import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.services.naver_scraper import ReportMeta, fetch_reports_with_pdf
from app.services.pdf_extractor import extract_text_from_pdf_url
from app.services.report_analyzer import AnalysisResult, analyze_reports
from app.services.ticker_resolver import search_tickers

logger = logging.getLogger(__name__)
router = APIRouter(tags=["research"])


# ── 응답 모델 ──────────────────────────────────────────────────────────────────

class TickerItem(BaseModel):
    ticker: str
    name: str
    market: str = ""


class ReportItem(BaseModel):
    nid: str
    title: str
    firm: str
    date: str
    detail_url: str
    pdf_url: str


class AnalyzeRequest(BaseModel):
    query: str | None = None      # 종목명 검색어 — 제공 시 search → top 1 자동 선택
    ticker: str | None = None
    name: str | None = None
    n: int = 5
    reports: list[ReportItem] | None = None


class TargetPrice(BaseModel):
    avg: float | None
    min: float | None
    max: float | None


class Opinions(BaseModel):
    buy: int
    neutral: int
    sell: int


class SourceItem(BaseModel):
    firm: str
    title: str
    date: str
    pdf_url: str


class AnalyzeResponse(BaseModel):
    ticker: str
    name: str
    report_count: int
    analyzed_at: str
    opinions: Opinions
    target_price: TargetPrice
    key_points: list[str]
    risks: list[str]
    sources: list[SourceItem]
    model_version: str


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/search", response_model=list[TickerItem], summary="종목명 검색")
async def search(
    q: str = Query(..., min_length=1, description="검색할 종목명"),
    limit: int = Query(default=10, ge=1, le=30),
):
    """종목명 부분 일치 검색. 네이버 증권 자동완성 API 기반."""
    results = await search_tickers(q, limit=limit)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"'{q}'에 해당하는 종목을 찾을 수 없습니다."},
        )
    return results


@router.get("/reports/{ticker}", response_model=list[ReportItem], summary="리포트 목록 수집")
async def get_reports(
    ticker: str,
    n: int = Query(default=5, ge=1, le=20, description="수집할 리포트 수"),
):
    """네이버 증권 리서치에서 해당 종목의 최신 리포트 목록과 PDF URL을 수집한다."""
    try:
        reports = await fetch_reports_with_pdf(ticker, n)
    except Exception as e:
        logger.error("리포트 수집 실패 (ticker=%s): %s", ticker, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "SCRAPE_FAILED", "message": "리포트 수집에 실패했습니다."},
        )

    if not reports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_REPORTS", "message": f"'{ticker}' 종목의 리포트를 찾을 수 없습니다."},
        )

    return [
        ReportItem(
            nid=r.nid,
            title=r.title,
            firm=r.firm,
            date=r.date,
            detail_url=r.detail_url,
            pdf_url=r.pdf_url,
        )
        for r in reports
    ]


@router.post("/analyze", response_model=AnalyzeResponse, summary="AI 통합 보고서 생성")
async def analyze(body: AnalyzeRequest):
    """
    리포트 목록 수집 → PDF 텍스트 추출 → Gemini 통합 분석 보고서 생성.

    - `query`를 제공하면 종목 검색 후 상위 1개 종목으로 자동 진행한다.
    - `ticker` + `name`을 직접 제공해도 된다.
    - `reports`를 함께 넣으면 스크래핑을 건너뛴다.
    """
    # ── 종목 결정 ─────────────────────────────────────────────────────────────
    if body.query:
        results = await search_tickers(body.query, limit=1)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": f"'{body.query}'에 해당하는 종목을 찾을 수 없습니다."},
            )
        ticker = results[0]["ticker"]
        name = results[0]["name"]
    elif body.ticker and body.name:
        ticker = body.ticker
        name = body.name
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_FIELDS", "message": "'query' 또는 'ticker'+'name'을 제공해야 합니다."},
        )

    # ── 리포트 수집 ───────────────────────────────────────────────────────────
    # query로 검색한 경우 reports 필드를 무시하고 항상 직접 수집한다.
    use_provided = body.reports is not None and not body.query
    if use_provided:
        reports: list[ReportMeta] = [
            ReportMeta(
                nid=r.nid,
                title=r.title,
                firm=r.firm,
                date=r.date,
                detail_url=r.detail_url,
                pdf_url=r.pdf_url,
            )
            for r in body.reports
        ]
    else:
        try:
            reports = await fetch_reports_with_pdf(ticker, body.n)
        except Exception as e:
            logger.error("리포트 수집 실패: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "SCRAPE_FAILED", "message": "리포트 수집에 실패했습니다."},
            )

    if not reports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_REPORTS", "message": "분석할 리포트가 없습니다."},
        )

    texts: list[str] = await asyncio.gather(
        *[extract_text_from_pdf_url(r.pdf_url) for r in reports]
    )

    try:
        result: AnalysisResult = await analyze_reports(
            ticker=ticker,
            name=name,
            reports=reports,
            texts=list(texts),
        )
    except Exception as e:
        logger.error("Gemini 분석 실패: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ANALYSIS_FAILED", "message": "보고서 생성에 실패했습니다."},
        )

    return AnalyzeResponse(
        ticker=result.ticker,
        name=result.name,
        report_count=result.report_count,
        analyzed_at=result.analyzed_at,
        opinions=Opinions(**result.opinions),
        target_price=TargetPrice(**result.target_price),
        key_points=result.key_points,
        risks=result.risks,
        sources=[SourceItem(**s) for s in result.sources],
        model_version=result.model_version,
    )
