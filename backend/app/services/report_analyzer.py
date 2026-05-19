import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from google import genai

from app.config import get_feature_config, get_settings
from app.services.metrics import enrich_quarters
from app.services.naver_scraper import ReportMeta

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    ticker: str
    name: str
    report_count: int
    analyzed_at: str
    target_price: dict
    sources: list[dict]
    model_version: str
    full_report: str | None = None
    dart_only: bool = False


# ── 데이터 블록 빌더 ────────────────────────────────────────────────────────────

def _has_usable_broker_texts(reports: list[dict]) -> bool:
    """하나라도 실제 본문이 추출된 리포트가 있으면 True."""
    return any(
        bool(r.get("text")) and r["text"] != "(본문 추출 실패 — 제목과 메타데이터만 사용)"
        for r in reports
    )


def _build_reports_block(reports: list[dict]) -> str:
    block = ""
    for i, r in enumerate(reports, 1):
        text = r.get("text") or "(본문 추출 실패 — 제목과 메타데이터만 사용)"
        block += (
            f"[리포트 {i}]\n"
            f"증권사: {r['firm']}\n"
            f"날짜: {r['date']}\n"
            f"제목: {r['title']}\n"
            f"본문:\n{text}\n\n"
        )
    return block


def _fmt(v: int | float | None, unit: str = "") -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:+.1f}%"
    return f"{v:,}{unit}"


def _fmt_eok(v: int | None) -> str:
    """원 단위 정수를 억원(소수점 1자리)으로 변환."""
    if v is None:
        return "N/A"
    return f"{round(v / 1e8, 1):,.0f}억"


def _build_is_table(dart_data: list[dict]) -> str:
    """손익계산서 Python 테이블 (억원 단위). §2에 직접 삽입용."""
    if not dart_data:
        return ""
    enriched = enrich_quarters(dart_data)
    lines = [
        "| 분기 | 매출액(억) | 영업이익(억) | OPM | 순이익(억) | NPM |",
        "|------|----------:|------------:|----:|----------:|----:|",
    ]
    for q in enriched:
        lines.append(
            f"| {q['period']}"
            f" | {_fmt_eok(q.get('revenue'))}"
            f" | {_fmt_eok(q.get('operating_income'))}"
            f" | {_fmt(q.get('opm'))}"
            f" | {_fmt_eok(q.get('net_income'))}"
            f" | {_fmt(q.get('npm'))}"
            f" |"
        )
    return "\n".join(lines)


def _inject_is_table(report_text: str, is_table: str) -> str:
    """§2 헤더 바로 다음 줄에 Python 생성 IS 테이블을 삽입."""
    import re
    if not is_table or not report_text:
        return report_text
    match = re.search(r"(##\s*2[\.。．].*?\n)", report_text)
    if not match:
        return report_text
    pos = match.end()
    return report_text[:pos] + "\n" + is_table + "\n\n" + report_text[pos:]


def _build_dart_block(dart_data: list[dict]) -> str:
    if not dart_data:
        return ""
    enriched = enrich_quarters(dart_data)

    lines = ["## DART 공시 재무 데이터 (최근 분기)"]
    lines.append("")

    # 손익계산서 테이블
    lines.append("### 손익계산서")
    lines.append("| 분기 | 매출액 | YoY | QoQ | 영업이익 | OPM | 순이익 | NPM |")
    lines.append("|------|-------:|----:|----:|---------:|----:|-------:|----:|")
    for q in enriched:
        lines.append(
            f"| {q['period']}"
            f" | {_fmt(q.get('revenue'), '원')}"
            f" | {_fmt(q.get('revenue_yoy'))}"
            f" | {_fmt(q.get('revenue_qoq'))}"
            f" | {_fmt(q.get('operating_income'), '원')}"
            f" | {_fmt(q.get('opm'))}"
            f" | {_fmt(q.get('net_income'), '원')}"
            f" | {_fmt(q.get('npm'))}"
            f" |"
        )

    lines.append("")
    # 현금흐름 / 운전자본 테이블
    lines.append("### 현금흐름 및 운전자본")
    lines.append("| 분기 | 영업CF | CapEx | FCF | 재고자산 | 매출채권 | 순차입금 |")
    lines.append("|------|-------:|------:|----:|---------:|---------:|---------:|")
    for q in enriched:
        capex_abs = abs(q["capex"]) if q.get("capex") is not None else None
        lines.append(
            f"| {q['period']}"
            f" | {_fmt(q.get('cfo'), '원')}"
            f" | {_fmt(capex_abs, '원')}"
            f" | {_fmt(q.get('fcf'), '원')}"
            f" | {_fmt(q.get('inventory'), '원')}"
            f" | {_fmt(q.get('receivables'), '원')}"
            f" | {_fmt(q.get('net_debt'), '원')}"
            f" |"
        )

    lines.append("")
    # 재무상태표 테이블
    lines.append("### 재무상태표 (기말 기준)")
    lines.append("| 분기 | 현금 | 총자산 | 자본총계 | 단기차입금 | 장기차입금 |")
    lines.append("|------|-----:|-------:|---------:|-----------:|-----------:|")
    for q in enriched:
        lines.append(
            f"| {q['period']}"
            f" | {_fmt(q.get('cash'), '원')}"
            f" | {_fmt(q.get('total_assets'), '원')}"
            f" | {_fmt(q.get('equity'), '원')}"
            f" | {_fmt(q.get('short_term_debt'), '원')}"
            f" | {_fmt(q.get('long_term_debt'), '원')}"
            f" |"
        )

    return "\n".join(lines) + "\n"


def _build_dart_filings_block(dart_filings: list[dict]) -> str:
    if not dart_filings:
        return ""
    lines = ["## DART 공시 문서 원문 (최근 정기공시)"]
    for i, f in enumerate(dart_filings, 1):
        lines.append(f"\n[공시 {i}: {f['title']} ({f['date']})]\n{f['text']}")
    return "\n".join(lines) + "\n"


# ── 프롬프트 빌더 ───────────────────────────────────────────────────────────────

_DATA_ABSENCE_RULE = """\
4. 각 섹션은 해당 섹션에 필요한 데이터가 입력에 포함된 경우에만 작성한다.
   데이터가 없는 섹션은 제목 아래에 '데이터 없음 — [이유]' 한 줄만 기재하고,
   일반 지식이나 추론으로 내용을 채우지 않는다."""

_SECTION_ABSENCE = {
    "broker":   "데이터 없음 — 증권사 리포트 미제공 또는 본문 추출 실패",
    "dart_fin": "데이터 없음 — DART 재무 데이터 미수집",
    "dart_doc": "데이터 없음 — 공시 원문 미수집",
}


def _build_full_report_prompt(
    name: str,
    reports_block: str,
    dart_block: str,
    dart_filings_block: str,
    broker_texts_available: bool,
) -> str:
    extra_rules = []
    if not broker_texts_available:
        extra_rules.append(
            "5. 증권사 리포트 본문이 모두 추출되지 않았다. "
            "§6(증권사 뷰)·§7(기대치 검증) 섹션에 "
            f"'{_SECTION_ABSENCE['broker']}' 한 줄만 기재하라."
        )
    if not dart_block.strip():
        extra_rules.append(
            "6. DART 재무 데이터가 제공되지 않았다. "
            "§2(재무 성과)·§3(현금흐름)·§4(사업부문) 섹션에 "
            f"'{_SECTION_ABSENCE['dart_fin']}' 한 줄만 기재하라."
        )
    if not dart_filings_block.strip():
        extra_rules.append(
            "7. DART 공시 원문이 제공되지 않았다. "
            "§5(공시 변화) 섹션에 "
            f"'{_SECTION_ABSENCE['dart_doc']}' 한 줄만 기재하라."
        )
    extra = ("\n" + "\n".join(extra_rules)) if extra_rules else ""

    return f"""당신은 대한민국 상장 기업 전문 기관투자자급 주식 리서치 애널리스트입니다.
제공된 데이터만을 근거로 심층 투자 리포트를 한국어로 작성하라.

[기업명] {name}

데이터 원칙
1. 분석 근거는 제공된 DART 재무 데이터와 증권사 리포트로 한정한다.
2. 수치는 입력 데이터에 명시된 검증 가능한 숫자만 인용하며, 확인 불가한 사항은 "제공 데이터 내 확인 불가"로 명시한다.
3. [공시 기반 사실(Fact)], [증권사 시각(Market View)], [분석(Analysis)]을 명확히 구분하여 기술한다.
{_DATA_ABSENCE_RULE}{extra}

보고서 구성 (반드시 아래 10개 섹션을 순서대로 작성)

## 1. 투자 요약 (Investment Summary)
- 공시와 리포트를 통해 확인된 핵심 투자 논지(Thesis)와 리스크를 3줄 이내로 요약한다.
- 이용 가능한 데이터 범위 내에서만 작성하고, 없는 정보는 '확인 불가'로 표기한다.

## 2. 사업 및 재무 성과 분석
- 재무 테이블은 자동 삽입되므로 직접 작성하지 말 것.
- 제공된 DART 재무 데이터를 기반으로 매출·영업이익·순이익 변동 원인과 트렌드 분석 텍스트만 서술하라.

## 3. 현금흐름 및 운전자본 분석
- 제공된 영업CF, CapEx, FCF, 재고자산, 매출채권, 순차입금 데이터를 분석한다.
- 순이익 대비 영업CF 괴리가 있다면 이익의 질(earnings quality) 관점에서 해석한다.
- 재고·매출채권 증가는 수요 둔화·회수 지연 리스크와 연결하여 해석한다.

## 4. 사업부문 및 성장 투자 분석
- 공시 원문의 주요 제품·서비스, 매출 및 수주상황 섹션을 바탕으로 세그먼트 변화를 분석한다.
- CapEx, R&D 비용 변화를 성장 투자 강도의 지표로 해석한다.
- 수주잔고가 있다면 향후 매출 가시성 관점에서 분석한다.

## 5. 공시 변화 분석 (Filing Delta)
- 최신 공시를 이전 공시와 비교하여 **새롭게 추가·삭제·수정된 핵심 문구**를 포착하라.
- [사업의 내용] 내 신규 사업·고객사 변동, [재무제표 주석]의 우발부채·소송, [투자자 보호 사항]의 리스크·전략 변화를 중점 분석한다.
- 변경 항목은 표(섹션 | 변경유형 | 이전 문구 | 최신 문구 | 해석 | 중요도)로 정리한다.

## 6. 증권사 뷰 및 컨센서스 분석
- 증권사별 투자의견, 목표주가, 직전 대비 변화, 핵심 투자 포인트를 표로 정리한다.
- 공통 투자 포인트, 의견 차이, 핵심 가정(성장률·마진·멀티플)을 분석한다.
- **목표주가 자체보다 목표주가를 만든 핵심 가정이 무엇인지 분석하라.**

## 7. 공시 데이터 vs 증권사 기대치 검증
- **비교 대상은 DART 재무 데이터의 최신 1개 분기**로 한정한다.
- 증권사 리포트에서 해당 분기에 대한 수치 추정(매출액, 영업이익, 순이익 등)을 추출하고, DART 실제값과 비교하라.
- 판정 형식: 수치 비교가 가능한 항목은 반드시 '**+n.n% 상회**' 또는 '**-n.n% 하회**' 형태로 계산하여 표기한다. 수치 비교가 불가한 항목은 '**확인 불가**'로 표기한다.
- 표(증권사 추정 | 실제(DART) | 판정)로 정리한다.

## 8. 핵심 리스크 요인
- DART 공시와 증권사 리포트에서 확인된 리스크를 표(리스크 | 출처 | 심각도 | 근거 | 투자 영향)로 정리한다.
- 심각도: High / Medium / Low, 출처: DART / Broker Report / Both

## 9. 다음 분기 체크포인트
- 현재 분석에서 가장 불확실한 항목 3~5개를 선정한다.
- 각각에 대해 표(체크포인트 | 확인 이유 | 긍정 신호 | 부정 신호)로 정리한다.

## 10. 최종 종합 평가
- 공시 펀더멘탈과 증권사 기대치 간의 간극을 종합하여 결론을 제시한다.
- 투자 관점: 긍정 / 중립 / 주의 중 하나로 명시하고, 조건부 판단 기준을 함께 제시한다.

작성 지침
- 단순 수치 나열을 지양하고 변화의 원인과 투자 의미 중심으로 서술한다.
- 핵심 문장은 볼드(**) 처리한다.
- 범용 산업 설명은 배제하고 이 기업 고유 데이터에만 집중한다.

{dart_block}
{dart_filings_block}
## 증권사 리포트 데이터
{reports_block}"""


def _build_dart_only_prompt(
    name: str,
    dart_block: str,
    dart_filings_block: str,
) -> str:
    dart_fin_available = bool(dart_block.strip())
    dart_doc_available = bool(dart_filings_block.strip())

    extra_rules = [
        "5. 증권사 리포트가 제공되지 않았다. §6·§7 섹션에 "
        f"'{_SECTION_ABSENCE['broker']}' 한 줄만 기재하라."
    ]
    if not dart_fin_available:
        extra_rules.append(
            "6. DART 재무 데이터가 제공되지 않았다. §2·§3·§4 섹션에 "
            f"'{_SECTION_ABSENCE['dart_fin']}' 한 줄만 기재하라."
        )
    if not dart_doc_available:
        extra_rules.append(
            "7. DART 공시 원문이 제공되지 않았다. §5 섹션에 "
            f"'{_SECTION_ABSENCE['dart_doc']}' 한 줄만 기재하라."
        )
    extra = "\n" + "\n".join(extra_rules)

    return f"""당신은 대한민국 상장 기업 전문 기관투자자급 주식 리서치 애널리스트입니다.
증권사 리포트가 제공되지 않아 DART 공시 데이터만으로 투자 리포트를 한국어로 작성하라.

[기업명] {name}

데이터 원칙
1. 분석 근거는 제공된 DART 재무 데이터 및 공시 문서 원문으로 한정한다.
2. 수치는 입력 데이터에 명시된 검증 가능한 숫자만 인용하며, 확인 불가한 사항은 "제공 데이터 내 확인 불가"로 명시한다.
3. 증권사 리포트가 없으므로 컨센서스·목표주가 분석은 생략하고, 해당 항목에 그 사실을 명시한다.
{_DATA_ABSENCE_RULE}{extra}

보고서 구성 (반드시 아래 10개 섹션을 순서대로 작성)

## 1. 투자 요약 (Investment Summary)
- DART 공시를 통해 확인된 핵심 투자 논지와 리스크를 3줄 이내로 요약한다.

## 2. 사업 및 재무 성과 분석
- 재무 테이블은 자동 삽입되므로 직접 작성하지 말 것.
- 제공된 DART 재무 데이터를 기반으로 매출·영업이익·순이익 변동 원인과 트렌드 분석 텍스트만 서술하라.

## 3. 현금흐름 및 운전자본 분석
- 영업CF, CapEx, FCF, 재고자산, 매출채권, 순차입금 데이터를 분석한다.
- 이익의 질(영업CF vs 순이익)과 운전자본 리스크를 해석한다.

## 4. 사업부문 및 성장 투자 분석
- 공시 원문의 주요 제품·서비스, 수주상황, CapEx·R&D 변화를 분석한다.

## 5. 공시 변화 분석 (Filing Delta)
- 최신 공시와 이전 공시를 비교하여 핵심 문구 변화를 표로 정리한다.

## 6. 증권사 뷰 및 컨센서스 분석
데이터 없음 — 증권사 리포트 미제공

## 7. 공시 데이터 vs 증권사 기대치 검증
데이터 없음 — 증권사 리포트 미제공

## 8. 핵심 리스크 요인
- DART 공시에서 확인된 실질적 위험 요인을 표로 정리한다.

## 9. 다음 분기 체크포인트
- 가장 불확실한 항목 3~5개를 선정하고, 긍정/부정 신호를 표로 정리한다.

## 10. 최종 종합 평가
- 공시 펀더멘탈 기준 결론과 투자 관점(긍정/중립/주의)을 제시한다.
- 시장 컨센서스 부재 사실을 명시한다.

작성 지침
- 단순 수치 나열을 지양하고 변화의 원인과 투자 의미 중심으로 서술한다.
- 핵심 문장은 볼드(**) 처리한다.

{dart_block}
{dart_filings_block}"""


# ── 목표주가 추출 ───────────────────────────────────────────────────────────────

def _build_target_price_prompt(reports: list[dict]) -> str:
    block = _build_reports_block(reports)
    return f"""아래 증권사 리포트에서 각 리포트의 목표주가만 추출하세요.

## 응답 형식 (반드시 아래 JSON만 출력)
{{
  "report_target_prices": [null],
  "target_price": {{"avg": null, "min": null, "max": null}}
}}

참고: "report_target_prices"는 리포트 순서대로 목표주가를 배열로 반환 (미제시 시 null)

## 리포트 데이터
{block}"""


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    return json.loads(raw.strip())


# ── Gemini 호출 ─────────────────────────────────────────────────────────────────

async def _extract_target_prices(
    client: genai.Client,
    model: str,
    reports: list[dict],
) -> dict:
    prompt = _build_target_price_prompt(reports)
    response = await client.aio.models.generate_content(model=model, contents=prompt)
    if not response.text:
        return {"report_target_prices": [], "target_price": {"avg": None, "min": None, "max": None}}
    try:
        return _parse_json_response(response.text)
    except Exception:
        logger.warning("목표주가 JSON 파싱 실패 — 기본값 반환")
        return {"report_target_prices": [], "target_price": {"avg": None, "min": None, "max": None}}


async def _generate_full_report(
    client: genai.Client,
    model: str,
    name: str,
    reports: list[dict],
    dart_data: list[dict] | None,
    dart_filings: list[dict] | None = None,
    dart_only: bool = False,
) -> str | None:
    dart_block = _build_dart_block(dart_data or [])
    dart_filings_block = _build_dart_filings_block(dart_filings or [])

    if dart_only:
        prompt = _build_dart_only_prompt(name, dart_block, dart_filings_block)
    else:
        reports_block = _build_reports_block(reports)
        broker_texts_available = _has_usable_broker_texts(reports)
        prompt = _build_full_report_prompt(
            name, reports_block, dart_block, dart_filings_block, broker_texts_available
        )

    response = await client.aio.models.generate_content(model=model, contents=prompt)
    text = response.text or None
    if text and dart_data:
        text = _inject_is_table(text, _build_is_table(dart_data))
    return text


# ── 진입점 ──────────────────────────────────────────────────────────────────────

async def analyze_reports(
    ticker: str,
    name: str,
    reports: list[ReportMeta],
    texts: list[str],
    dart_data: list[dict] | None = None,
    dart_filings: list[dict] | None = None,
    dart_only: bool = False,
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

    client = genai.Client(api_key=settings.gemini_api_key)

    if dart_only:
        full_report = await _generate_full_report(
            client, feat.model, name, [], dart_data, dart_filings, dart_only=True
        )
        target_price = {"avg": None, "min": None, "max": None}
        sources = []
    else:
        target_parsed, full_report = await asyncio.gather(
            _extract_target_prices(client, feat.model, report_dicts),
            _generate_full_report(client, feat.model, name, report_dicts, dart_data, dart_filings),
        )
        target = target_parsed.get("target_price", {}) or {}
        target_price = {
            "avg": target.get("avg"),
            "min": target.get("min"),
            "max": target.get("max"),
        }
        report_target_prices = target_parsed.get("report_target_prices", [])
        sources = [
            {
                "firm": r.firm,
                "title": r.title,
                "date": r.date,
                "pdf_url": r.pdf_url,
                "target_price": report_target_prices[i] if i < len(report_target_prices) else None,
            }
            for i, r in enumerate(reports)
        ]

    return AnalysisResult(
        ticker=ticker,
        name=name,
        report_count=len(reports),
        analyzed_at=datetime.now(timezone(timedelta(hours=9))).date().isoformat(),
        target_price=target_price,
        sources=sources,
        model_version=feat.model,
        full_report=full_report,
        dart_only=dart_only,
    )
