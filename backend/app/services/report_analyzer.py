import json
import logging
from dataclasses import dataclass
from datetime import date

from google import genai

from app.config import get_feature_config, get_settings
from app.services.naver_scraper import ReportMeta

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    ticker: str
    name: str
    report_count: int
    analyzed_at: str
    opinions: dict        # {"buy": n, "neutral": n, "sell": n}
    target_price: dict    # {"avg": n, "min": n, "max": n} — 없으면 None
    key_points: list[str]
    risks: list[str]
    sources: list[dict]   # [{"firm", "title", "date", "pdf_url"}]
    model_version: str


def _build_prompt(ticker: str, name: str, reports: list[dict]) -> str:
    reports_block = ""
    for i, r in enumerate(reports, 1):
        text = r.get("text") or "(본문 추출 실패 — 제목과 메타데이터만 사용)"
        reports_block += (
            f"[리포트 {i}]\n"
            f"증권사: {r['firm']}\n"
            f"날짜: {r['date']}\n"
            f"제목: {r['title']}\n"
            f"본문:\n{text}\n\n"
        )

    return f"""당신은 한국 주식 리서치 분석 전문가입니다.
아래 {name}({ticker})에 대한 {len(reports)}개의 증권사 리포트를 분석하여 투자자에게 유용한 통합 보고서를 작성하세요.

## 지시사항
1. 각 리포트의 투자의견(매수/중립/매도)과 목표주가를 파악하세요. 명시되지 않은 경우 null로 처리하세요.
2. 공통적으로 언급되는 핵심 투자 포인트를 중요도 순으로 정리하세요.
3. 주요 리스크 요인을 정리하세요.
4. 한국어로 작성하세요.

## 응답 형식 (반드시 아래 JSON만 출력)
{{
  "opinions": {{"buy": 0, "neutral": 0, "sell": 0}},
  "target_price": {{"avg": null, "min": null, "max": null}},
  "key_points": ["포인트1", "포인트2", "포인트3"],
  "risks": ["리스크1", "리스크2"]
}}

## 리포트 데이터
{reports_block}"""


def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    return json.loads(raw.strip())


async def analyze_reports(
    ticker: str,
    name: str,
    reports: list[ReportMeta],
    texts: list[str],
) -> AnalysisResult:
    settings = get_settings()
    feat = get_feature_config("krx_report")

    report_dicts = [
        {
            "firm": r.firm,
            "date": r.date,
            "title": r.title,
            "text": texts[i] if i < len(texts) else "",
        }
        for i, r in enumerate(reports)
    ]

    prompt = _build_prompt(ticker, name, report_dicts)

    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=feat.model,
        contents=prompt,
    )

    if not response.text:
        raise ValueError("Gemini returned empty response (possible safety filter or empty input)")

    parsed = _parse_response(response.text)

    target = parsed.get("target_price", {}) or {}
    target_price = {
        "avg": target.get("avg"),
        "min": target.get("min"),
        "max": target.get("max"),
    }

    sources = [
        {
            "firm": r.firm,
            "title": r.title,
            "date": r.date,
            "pdf_url": r.pdf_url,
        }
        for r in reports
    ]

    return AnalysisResult(
        ticker=ticker,
        name=name,
        report_count=len(reports),
        analyzed_at=date.today().isoformat(),
        opinions=parsed.get("opinions", {"buy": 0, "neutral": 0, "sell": 0}),
        target_price=target_price,
        key_points=parsed.get("key_points", []),
        risks=parsed.get("risks", []),
        sources=sources,
        model_version=feat.model,
    )
