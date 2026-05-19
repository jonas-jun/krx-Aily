"""보고서 중간 데이터 모델.

수치와 해석을 분리하고, 섹션별 필수 필드를 강제하여
report_analyzer 프롬프트 렌더링의 일관성을 보장한다.
"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


# ── Enum 정의 ──────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ChangeType(str, Enum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"


class Judgment(str, Enum):
    MATCH = "일치"
    PARTIAL = "일부 일치"
    MISMATCH = "불일치"
    UNVERIFIABLE = "확인 불가"


# ── 분기 재무 데이터 ────────────────────────────────────────────────────────────

class QuarterData(BaseModel):
    period: str                          # e.g. "2024 3Q"

    # 손익계산서
    revenue: int | None = None
    gross_profit: int | None = None
    sga: int | None = None
    operating_income: int | None = None
    net_income: int | None = None

    # 재무상태표 (기말 스냅샷)
    cash: int | None = None
    receivables: int | None = None
    inventory: int | None = None
    total_assets: int | None = None
    equity: int | None = None
    short_term_debt: int | None = None
    long_term_debt: int | None = None

    # 현금흐름표
    cfo: int | None = None
    cfi: int | None = None
    cff: int | None = None
    capex: int | None = None            # CF표 원본값 (음수), abs 처리 후 FCF 계산

    # 파생 지표 (metrics.enrich_quarters 에서 채워짐)
    gpm: float | None = None            # 매출총이익률 (%)
    opm: float | None = None            # 영업이익률 (%)
    npm: float | None = None            # 순이익률 (%)
    fcf: int | None = None              # 잉여현금흐름
    net_debt: int | None = None         # 순차입금
    revenue_yoy: float | None = None    # 매출 YoY (%)
    revenue_qoq: float | None = None    # 매출 QoQ (%)
    oi_yoy: float | None = None         # 영업이익 YoY (%)
    oi_qoq: float | None = None         # 영업이익 QoQ (%)


# ── 공시 변화 분석 ──────────────────────────────────────────────────────────────

class FilingChange(BaseModel):
    section: str
    change_type: ChangeType
    before: str | None = None
    after: str | None = None
    interpretation: str
    severity: Severity


# ── 증권사 뷰 ───────────────────────────────────────────────────────────────────

class BrokerView(BaseModel):
    firm: str
    date: str
    opinion: str | None = None          # 매수 / 중립 / 매도 등
    target_price: int | None = None
    prev_target_price: int | None = None
    key_thesis: str = ""
    key_risk: str = ""


# ── 기대치 검증 ─────────────────────────────────────────────────────────────────

class ExpectationCheck(BaseModel):
    broker_expectation: str
    verification_data: str
    actual_result: str
    judgment: Judgment


# ── 리스크 요인 ─────────────────────────────────────────────────────────────────

class RiskFactor(BaseModel):
    risk: str
    source: str                         # "DART" | "Broker Report" | "Both"
    severity: Severity
    evidence: str
    impact: str


# ── 체크포인트 ──────────────────────────────────────────────────────────────────

class Checkpoint(BaseModel):
    item: str
    reason: str
    positive_signal: str
    negative_signal: str


# ── 최상위 보고서 모델 ──────────────────────────────────────────────────────────

class ResearchReport(BaseModel):
    ticker: str
    name: str
    quarters: list[QuarterData] = Field(default_factory=list)
    filing_changes: list[FilingChange] = Field(default_factory=list)
    broker_views: list[BrokerView] = Field(default_factory=list)
    expectation_checks: list[ExpectationCheck] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)

    @classmethod
    def from_raw(
        cls,
        ticker: str,
        name: str,
        dart_quarters: list[dict],
    ) -> "ResearchReport":
        """dart_service에서 받은 분기 데이터로 ResearchReport 초기화."""
        quarters = [QuarterData(**{k: v for k, v in q.items() if k in QuarterData.model_fields}) for q in dart_quarters]
        return cls(ticker=ticker, name=name, quarters=quarters)
