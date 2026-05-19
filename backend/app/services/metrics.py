"""파생 지표 계산 모듈.

LLM이 아닌 코드에서 YoY/QoQ/마진율/FCF 등을 계산하여
report_analyzer 프롬프트에 주입한다.
"""

from __future__ import annotations


def _pct(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(numerator / denominator * 100, 1)


def _growth(current: int | None, base: int | None) -> float | None:
    if current is None or base is None or base == 0:
        return None
    return round((current - base) / abs(base) * 100, 1)


def compute_margin(profit: int | None, revenue: int | None) -> float | None:
    return _pct(profit, revenue)


def compute_yoy(current: int | None, prior: int | None) -> float | None:
    return _growth(current, prior)


def compute_qoq(current: int | None, prior: int | None) -> float | None:
    return _growth(current, prior)


def compute_fcf(cfo: int | None, capex: int | None) -> int | None:
    """FCF = 영업CF − |CapEx|. capex는 CF표에서 음수로 저장되므로 부호 처리."""
    if cfo is None:
        return None
    capex_abs = abs(capex) if capex is not None else 0
    return cfo - capex_abs


def compute_net_debt(
    short_term_debt: int | None,
    long_term_debt: int | None,
    cash: int | None,
) -> int | None:
    total_debt = (short_term_debt or 0) + (long_term_debt or 0)
    if total_debt == 0 and cash is None:
        return None
    return total_debt - (cash or 0)


def compute_debt_ratio(total_liabilities: int | None, equity: int | None) -> float | None:
    return _pct(total_liabilities, equity)


def enrich_quarters(quarters: list[dict]) -> list[dict]:
    """분기 데이터 리스트에 파생 지표를 추가하여 반환.

    - GPM, OPM, NPM (마진율)
    - FCF, 순차입금
    - revenue_yoy, revenue_qoq, oi_yoy (성장률)
    - 직전 분기 / 전년 동기를 리스트 내 위치로 추정
    """
    enriched = [dict(q) for q in quarters]

    for i, q in enumerate(enriched):
        rev = q.get("revenue")

        # 마진율
        q["gpm"] = compute_margin(q.get("gross_profit"), rev)
        q["opm"] = compute_margin(q.get("operating_income"), rev)
        q["npm"] = compute_margin(q.get("net_income"), rev)

        # FCF / 순차입금
        q["fcf"] = compute_fcf(q.get("cfo"), q.get("capex"))
        q["net_debt"] = compute_net_debt(
            q.get("short_term_debt"), q.get("long_term_debt"), q.get("cash")
        )

        # QoQ: 직전 분기 (i-1)
        if i > 0:
            prev = enriched[i - 1]
            q["revenue_qoq"] = compute_qoq(rev, prev.get("revenue"))
            q["oi_qoq"] = compute_qoq(q.get("operating_income"), prev.get("operating_income"))
        else:
            q["revenue_qoq"] = None
            q["oi_qoq"] = None

        # YoY: 전년 동기 (동일 분기 레이블이 4개 이전에 있는 경우)
        # 예: 리스트가 [2023 3Q, 2023 4Q, 2024 1Q, 2024 2Q, 2024 3Q] 일 때
        # 2024 3Q의 YoY 기준은 2023 3Q (index i-4)
        yoy_base = enriched[i - 4] if i >= 4 else None
        if yoy_base:
            q["revenue_yoy"] = compute_yoy(rev, yoy_base.get("revenue"))
            q["oi_yoy"] = compute_yoy(q.get("operating_income"), yoy_base.get("operating_income"))
        else:
            q["revenue_yoy"] = None
            q["oi_yoy"] = None

    return enriched
