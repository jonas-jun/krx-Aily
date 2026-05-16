import asyncio
import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"

# DART 보고서 분기 코드 (reprt_code, 내부 레이블)
_REPRT_CODES = [
    ("11013", "1Q"),   # 1분기보고서   — Q1 누적
    ("11012", "반기"), # 반기보고서    — Q1+Q2 누적
    ("11014", "3Q"),   # 3분기보고서   — Q1+Q2+Q3 누적
    ("11011", "연간"), # 사업보고서    — 연간 누적
]

# corp_code 매핑 캐시 (ticker → corp_code)
_corp_code_map: dict[str, str] | None = None


async def _load_corp_code_map() -> dict[str, str]:
    """DART corpCode.xml.zip을 다운로드하여 stock_code → corp_code 맵 반환 (모듈 레벨 캐시)."""
    global _corp_code_map
    if _corp_code_map is not None:
        return _corp_code_map

    settings = get_settings()
    url = f"{DART_BASE}/corpCode.xml?crtfc_key={settings.dart_api_key}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.error("corpCode.xml 다운로드 실패: %s", e)
        _corp_code_map = {}
        return _corp_code_map

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_bytes = zf.read("CORPCODE.xml")
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        logger.error("corpCode.xml 파싱 실패: %s", e)
        _corp_code_map = {}
        return _corp_code_map

    mapping: dict[str, str] = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            mapping[stock_code] = corp_code

    _corp_code_map = mapping
    logger.info("corpCode 매핑 로드 완료: %d개 종목", len(mapping))
    return _corp_code_map


async def get_corp_code(ticker: str) -> str:
    """6자리 ticker → DART corp_code (8자리). 매핑 실패 시 빈 문자열 반환."""
    mapping = await _load_corp_code_map()
    return mapping.get(ticker.zfill(6), "")


async def _fetch_cumulative_financials(
    client: httpx.AsyncClient,
    corp_code: str,
    year: int,
    reprt_code: str,
    label: str,
    dart_api_key: str,
) -> dict | None:
    """단일 보고서의 누적 재무 데이터(매출액, 영업이익, 당기순이익) 조회. 실패 시 None 반환."""
    url = (
        f"{DART_BASE}/fnlttSinglAcnt.json"
        f"?crtfc_key={dart_api_key}"
        f"&corp_code={corp_code}"
        f"&bsns_year={year}"
        f"&reprt_code={reprt_code}"
        f"&fs_div=CFS"  # 연결재무제표 우선
    )
    try:
        resp = await client.get(url)
        data = resp.json()
    except Exception as e:
        logger.warning("DART 재무 조회 실패 (%s %s): %s", year, label, e)
        return None

    if data.get("status") != "000":
        # 연결재무제표 없으면 별도재무제표 재시도
        url_ofs = url.replace("fs_div=CFS", "fs_div=OFS")
        try:
            resp = await client.get(url_ofs)
            data = resp.json()
        except Exception:
            return None
        if data.get("status") != "000":
            return None

    revenue = operating_income = net_income = None
    for row in data.get("list", []):
        account = row.get("account_nm", "")
        amount_str = row.get("thstrm_amount", "").replace(",", "").replace("-", "")
        try:
            amount = int(amount_str) if amount_str else None
        except ValueError:
            amount = None

        if "매출" in account and revenue is None:
            revenue = amount
        if "영업이익" in account and operating_income is None:
            operating_income = amount
        if "당기순이익" in account and net_income is None:
            net_income = amount

    if revenue is None and operating_income is None and net_income is None:
        return None

    return {
        "revenue": revenue,
        "operating_income": operating_income,
        "net_income": net_income,
    }


def _subtract_annual(annual: int | None, *quarters: int | None) -> int | None:
    """연간 누적에서 개별 분기 합산을 차감하여 4Q 단독 수치 반환."""
    if annual is None:
        return None
    return annual - sum(v or 0 for v in quarters)


def _compute_actual_quarters(cumulative: dict[str, dict], year: int) -> list[dict]:
    """분기 보고서는 개별 수치 그대로, 4Q만 연간 누적 − (1Q+2Q+3Q)로 역산."""
    q1 = cumulative.get("1Q")
    q2 = cumulative.get("반기")  # 반기보고서: Q2 개별 수치
    q3 = cumulative.get("3Q")   # 3분기보고서: Q3 개별 수치
    ann = cumulative.get("연간") # 사업보고서: 연간 누적

    quarters = []

    if q1:
        quarters.append({
            "period": f"{year} 1Q",
            "revenue": q1["revenue"],
            "operating_income": q1["operating_income"],
            "net_income": q1["net_income"],
        })
    if q2:
        quarters.append({
            "period": f"{year} 2Q",
            "revenue": q2["revenue"],
            "operating_income": q2["operating_income"],
            "net_income": q2["net_income"],
        })
    if q3:
        quarters.append({
            "period": f"{year} 3Q",
            "revenue": q3["revenue"],
            "operating_income": q3["operating_income"],
            "net_income": q3["net_income"],
        })

    # 4Q = 연간 누적 − (1Q + 2Q + 3Q 개별 합산)
    # 정확도 보장을 위해 3개 분기 모두 있을 때만 계산
    if ann and q1 and q2 and q3:
        quarters.append({
            "period": f"{year} 4Q",
            "revenue": _subtract_annual(ann["revenue"], q1["revenue"], q2["revenue"], q3["revenue"]),
            "operating_income": _subtract_annual(ann["operating_income"], q1["operating_income"], q2["operating_income"], q3["operating_income"]),
            "net_income": _subtract_annual(ann["net_income"], q1["net_income"], q2["net_income"], q3["net_income"]),
        })

    return quarters


async def fetch_last_4_quarters_reports(corp_code: str) -> list[dict]:
    """최근 4개 분기 개별 실적(매출액, 영업이익, 당기순이익) 수집. 실패 시 빈 리스트 반환."""
    if not corp_code:
        return []

    settings = get_settings()
    if not settings.dart_api_key:
        logger.warning("DART_API_KEY가 설정되지 않아 공시 데이터를 건너뜁니다.")
        return []

    current_year = datetime.now().year
    years = [current_year - 1, current_year]  # 오래된 연도 → 최신 연도 순 (시간순 정렬 보장)

    all_tasks = []
    task_meta: list[tuple[int, str]] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for year in years:
            for reprt_code, label in _REPRT_CODES:
                all_tasks.append(
                    _fetch_cumulative_financials(
                        client, corp_code, year, reprt_code, label, settings.dart_api_key
                    )
                )
                task_meta.append((year, label))

        results = await asyncio.gather(*all_tasks, return_exceptions=True)

    # 연도별 누적 데이터 정리
    cumulative_by_year: dict[int, dict[str, dict]] = {year: {} for year in years}
    for (year, label), res in zip(task_meta, results):
        if isinstance(res, dict):
            cumulative_by_year[year][label] = res

    # 실제 분기 수치 계산 후 합산 (오래된 → 최신 순으로 all_quarters가 구성됨)
    all_quarters: list[dict] = []
    for year in years:
        all_quarters.extend(_compute_actual_quarters(cumulative_by_year[year], year))

    # 가장 최근 5개 분기만 반환 (이미 시간순 오름차순)
    return all_quarters[-5:]


async def fetch_dart_data(ticker: str) -> list[dict]:
    """ticker 기준 DART 공시 재무 데이터 수집 진입점. 실패 시 빈 리스트 반환."""
    try:
        corp_code = await get_corp_code(ticker)
        if not corp_code:
            logger.info("corp_code 매핑 실패 (ticker=%s)", ticker)
            return []
        return await fetch_last_4_quarters_reports(corp_code)
    except Exception as e:
        logger.error("DART 데이터 수집 중 예외 (ticker=%s): %s", ticker, e)
        return []
