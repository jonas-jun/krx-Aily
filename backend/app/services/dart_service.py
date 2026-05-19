import asyncio
import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"

_FILING_TEXT_LIMIT = 15_000
_FILING_HTML_FILES = 5

# IS 필드: 개별 분기값 (반기보고서=Q2 개별, 3Q보고서=Q3 개별)
# 4Q = annual − (Q1 + Q2 + Q3)
_IS_FIELDS = ("revenue", "gross_profit", "sga", "operating_income", "net_income")
# CF 필드: 누적 YTD값 (반기보고서=H1 누적, 3Q보고서=9M 누적)
# Q2 = H1 − Q1 / Q3 = 9M − H1 / 4Q = annual − 9M
_CF_FIELDS = ("cfo", "cfi", "cff", "capex")
# BS 필드: 기말 스냅샷 값 — 4Q는 연간 보고서 값 그대로
_BS_FIELDS = (
    "cash", "receivables", "inventory", "total_assets",
    "equity", "short_term_debt", "long_term_debt",
)
# 하위 호환: report_analyzer 등에서 참조하는 통합 튜플
_IS_CF_FIELDS = _IS_FIELDS + _CF_FIELDS

# (field_name, sj_div, match_keywords, exclude_keywords)
# sj_div는 문자열 또는 문자열 리스트(복수 허용). IS 항목은 CIS(포괄손익계산서)도 fallback으로 검색.
# fnlttSinglAcntAll 응답 rows에서 계정별 첫 번째 매칭 값을 추출하는 패턴
_ACCOUNT_PATTERNS: list[tuple[str, str | list[str], list[str], list[str]]] = [
    # 손익계산서 (IS / CIS) — CIS만 제출하는 기업(NAVER, 삼성바이오 등) 대응
    # "기타영업수익"이 "영업수익" 키워드에 매칭되는 것을 막기 위해 "기타"를 excludes에 추가
    # "매출" 단독 키워드는 너무 광범위(매출채권·매출원가도 포함될 수 있음)하여 제거
    ("revenue",          ["IS", "CIS"], ["매출액", "수익(매출액)", "매출수익", "영업수익"],  ["원가", "채권", "총이익", "총손실", "기타"]),
    ("gross_profit",     ["IS", "CIS"], ["매출총이익"],                          []),
    ("sga",              ["IS", "CIS"], ["판매비와관리비", "판관비"],             []),
    ("operating_income", ["IS", "CIS"], ["영업이익"],                            ["영업외"]),
    # 분기보고서 → "분기순이익(손실)", 반기보고서 → "반기순이익(손실)", 연간 → "당기순이익"
    ("net_income",       ["IS", "CIS"], ["분기순이익", "반기순이익", "당기순이익"],  ["비지배", "지배기업 소유주"]),
    # 재무상태표 (BS)
    ("cash",             "BS", ["현금및현금성자산", "현금 및 현금성자산"], []),
    ("receivables",      "BS", ["매출채권"],                            []),
    ("inventory",        "BS", ["재고자산"],                            []),
    ("total_assets",     "BS", ["자산총계"],                            []),
    ("equity",           "BS", ["자본총계"],                            []),
    ("short_term_debt",  "BS", ["단기차입금"],                          []),
    ("long_term_debt",   "BS", ["장기차입금"],                          []),
    # 현금흐름표 (CF)  — capex는 유출이므로 음수 저장, metrics.py에서 abs 처리
    ("cfo",   "CF", ["영업활동"],                              []),
    ("cfi",   "CF", ["투자활동"],                              []),
    ("cff",   "CF", ["재무활동"],                              []),
    ("capex", "CF", ["유형자산의 취득", "유형자산취득"],        []),
]

_REPRT_CODES = [
    ("11013", "1Q"),
    ("11012", "반기"),
    ("11014", "3Q"),
    ("11011", "연간"),
]

_corp_code_map: dict[str, str] | None = None


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


async def _load_corp_code_map() -> dict[str, str]:
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
    mapping = await _load_corp_code_map()
    return mapping.get(ticker.zfill(6), "")


def _first_amount(
    rows: list[dict],
    sj_div: str | list[str],
    keywords: list[str],
    excludes: list[str],
) -> int | None:
    """sj_div가 일치하고 keywords 중 하나를 포함하며 excludes를 포함하지 않는 첫 행의 금액 반환.

    sj_div는 단일 문자열 또는 리스트 허용. 리스트인 경우 순서대로 시도하여 첫 번째 매칭 반환.
    IS/CIS 둘 다 지원하기 위해 ["IS", "CIS"] 형태로 전달할 수 있다.
    """
    allowed = {sj_div} if isinstance(sj_div, str) else set(sj_div)
    for row in rows:
        if row.get("sj_div") not in allowed:
            continue
        account = row.get("account_nm", "")
        if excludes and any(ex in account for ex in excludes):
            continue
        if not any(kw in account for kw in keywords):
            continue
        raw = (row.get("thstrm_amount") or "").replace(",", "")
        try:
            return int(raw) if raw else None
        except ValueError:
            continue
    return None


def _parse_account_rows(rows: list[dict]) -> dict:
    """fnlttSinglAcntAll 응답 rows → 전체 재무 필드 플랫 딕셔너리."""
    result: dict[str, int | None] = {}
    for field, sj_div, keywords, excludes in _ACCOUNT_PATTERNS:
        if field not in result:
            result[field] = _first_amount(rows, sj_div, keywords, excludes)
    return result


async def _fetch_full_financials(
    client: httpx.AsyncClient,
    corp_code: str,
    year: int,
    reprt_code: str,
    label: str,
    dart_api_key: str,
) -> dict | None:
    """fnlttSinglAcntAll로 전체 재무제표 조회. CFS 우선 → OFS 폴백. 실패 시 None."""
    base = (
        f"?crtfc_key={dart_api_key}"
        f"&corp_code={corp_code}"
        f"&bsns_year={year}"
        f"&reprt_code={reprt_code}"
    )
    for fs_div in ("CFS", "OFS"):
        url = f"{DART_BASE}/fnlttSinglAcntAll.json{base}&fs_div={fs_div}"
        try:
            resp = await client.get(url)
            data = resp.json()
        except Exception as e:
            logger.warning("DART 전체계정 조회 실패 (%s %s %s): %s", year, label, fs_div, e)
            continue
        if data.get("status") != "000":
            continue
        rows = data.get("list", [])
        if not rows:
            continue
        result = _parse_account_rows(rows)
        if any(result.get(f) is not None for f in ("revenue", "operating_income", "net_income")):
            return result
    logger.info("DART 재무 데이터 없음 (%s %s)", year, label)
    return None


def _subtract_annual(annual: int | None, *quarters: int | None) -> int | None:
    if annual is None:
        return None
    return annual - sum(v or 0 for v in quarters)


def _get(data: dict | None, field: str) -> int | None:
    return data.get(field) if data else None


def _diff(a: int | None, b: int | None) -> int | None:
    """a − b. 어느 쪽이라도 None이면 None 반환."""
    if a is None or b is None:
        return None
    return a - b


def _compute_actual_quarters(cumulative: dict[str, dict], year: int) -> list[dict]:
    """IS(개별 분기) / CF(누적 YTD → 개별 역산) / BS(기말 스냅샷) 분리 처리.

    IS:  반기=Q2 개별, 3Q=Q3 개별  → 4Q = annual − (Q1+Q2+Q3)
    CF:  반기=H1 누적, 3Q=9M 누적  → Q2=H1−Q1, Q3=9M−H1, 4Q=annual−9M
    BS:  각 보고서 기말 스냅샷       → 4Q = 연간 보고서 기말값
    """
    q1 = cumulative.get("1Q")
    q2 = cumulative.get("반기")
    q3 = cumulative.get("3Q")
    ann = cumulative.get("연간")

    quarters: list[dict] = []

    # ── 1Q ──────────────────────────────────────────────────────────────────────
    if q1:
        q: dict = {"period": f"{year} 1Q"}
        for f in _IS_FIELDS + _CF_FIELDS + _BS_FIELDS:
            q[f] = _get(q1, f)
        quarters.append(q)

    # ── 2Q ──────────────────────────────────────────────────────────────────────
    if q2:
        q = {"period": f"{year} 2Q"}
        for f in _IS_FIELDS:                          # 반기보고서 IS = Q2 개별
            q[f] = _get(q2, f)
        for f in _CF_FIELDS:                          # 반기보고서 CF = H1 누적 → Q2 개별
            q[f] = _diff(_get(q2, f), _get(q1, f) if q1 else None)
        for f in _BS_FIELDS:                          # 6월 말 스냅샷
            q[f] = _get(q2, f)
        quarters.append(q)

    # ── 3Q ──────────────────────────────────────────────────────────────────────
    if q3:
        q = {"period": f"{year} 3Q"}
        for f in _IS_FIELDS:                          # 3Q보고서 IS = Q3 개별
            q[f] = _get(q3, f)
        for f in _CF_FIELDS:                          # 3Q보고서 CF = 9M 누적 → Q3 개별
            q[f] = _diff(_get(q3, f), _get(q2, f) if q2 else None)
        for f in _BS_FIELDS:                          # 9월 말 스냅샷
            q[f] = _get(q3, f)
        quarters.append(q)

    # ── 4Q ──────────────────────────────────────────────────────────────────────
    if ann:
        q = {"period": f"{year} 4Q"}
        if q1 and q2 and q3:
            for f in _IS_FIELDS:                      # 연간 − (Q1+Q2+Q3 개별)
                q[f] = _subtract_annual(_get(ann, f), _get(q1, f), _get(q2, f), _get(q3, f))
        else:
            for f in _IS_FIELDS:
                q[f] = _get(ann, f)                   # 분기 데이터 부족 시 연간값 사용
        for f in _CF_FIELDS:                          # 연간 CF − 9M 누적
            q[f] = _diff(_get(ann, f), _get(q3, f) if q3 else None)
        for f in _BS_FIELDS:                          # 12월 말 스냅샷
            q[f] = _get(ann, f)
        quarters.append(q)

    return quarters


async def fetch_last_4_quarters_reports(corp_code: str) -> list[dict]:
    """최근 5개 분기 재무 데이터(IS + BS + CF) 수집. 실패 시 빈 리스트 반환."""
    if not corp_code:
        return []

    settings = get_settings()
    if not settings.dart_api_key:
        logger.warning("DART_API_KEY가 설정되지 않아 공시 데이터를 건너뜁니다.")
        return []

    current_year = datetime.now().year
    years = [current_year - 1, current_year]

    all_tasks = []
    task_meta: list[tuple[int, str]] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for year in years:
            for reprt_code, label in _REPRT_CODES:
                all_tasks.append(
                    _fetch_full_financials(
                        client, corp_code, year, reprt_code, label, settings.dart_api_key
                    )
                )
                task_meta.append((year, label))

        results = await asyncio.gather(*all_tasks, return_exceptions=True)

    cumulative_by_year: dict[int, dict[str, dict]] = {year: {} for year in years}
    for (year, label), res in zip(task_meta, results):
        if isinstance(res, dict):
            cumulative_by_year[year][label] = res

    all_quarters: list[dict] = []
    for year in years:
        all_quarters.extend(_compute_actual_quarters(cumulative_by_year[year], year))

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


async def _fetch_filing_documents(corp_code: str, max_count: int = 3) -> list[dict]:
    """최근 사업보고서·분기보고서 목록 조회 후 문서 ZIP을 다운로드하여 텍스트 추출."""
    settings = get_settings()
    if not settings.dart_api_key or not corp_code:
        return []

    # DART list.json API는 bgn_de 없이 pblntf_ty만 지정하면 013(데이터 없음)을 반환하는 경우가 있음
    bgn_de = str(datetime.now().year - 3) + "0101"
    async with httpx.AsyncClient(timeout=30) as client:
        list_url = (
            f"{DART_BASE}/list.json"
            f"?crtfc_key={settings.dart_api_key}"
            f"&corp_code={corp_code}"
            f"&pblntf_ty=A"
            f"&bgn_de={bgn_de}"
            f"&page_count={max_count}"
        )
        try:
            resp = await client.get(list_url)
            data = resp.json()
        except Exception as e:
            logger.warning("DART 공시 목록 조회 실패 (corp_code=%s): %s", corp_code, e)
            return []

        if data.get("status") != "000":
            logger.info("DART 공시 목록 없음 (corp_code=%s, status=%s)", corp_code, data.get("status"))
            return []

        results: list[dict] = []
        for filing in data.get("list", [])[:max_count]:
            rcept_no = filing.get("rcept_no", "")
            if not rcept_no:
                continue

            # DART 공시 원문 ZIP 다운로드: document.xml 엔드포인트 사용
            doc_url = (
                f"{DART_BASE}/document.xml"
                f"?crtfc_key={settings.dart_api_key}"
                f"&rcept_no={rcept_no}"
            )
            try:
                doc_resp = await client.get(doc_url)
                doc_resp.raise_for_status()
            except Exception as e:
                logger.warning("DART 문서 다운로드 실패 (rcept_no=%s): %s", rcept_no, e)
                continue

            try:
                with zipfile.ZipFile(io.BytesIO(doc_resp.content)) as zf:
                    # DART 문서는 .xml 또는 .html 형식으로 포함됨
                    doc_names = [
                        n for n in zf.namelist()
                        if n.lower().endswith(".xml") or n.lower().endswith(".html")
                    ]
                    parts: list[str] = []
                    for doc_name in doc_names[:_FILING_HTML_FILES]:
                        with zf.open(doc_name) as f:
                            raw = f.read()
                        try:
                            html_str = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            html_str = raw.decode("euc-kr", errors="replace")
                        text = _html_to_text(html_str)
                        if text:
                            parts.append(text)

                combined = "\n\n".join(parts)[:_FILING_TEXT_LIMIT]
                if combined:
                    results.append({
                        "title": filing.get("report_nm", ""),
                        "date": filing.get("rcept_dt", ""),
                        "text": combined,
                    })
            except Exception as e:
                logger.warning("DART ZIP 파싱 실패 (rcept_no=%s): %s", rcept_no, e)

    return results


async def fetch_dart_filing_texts(ticker: str, max_count: int = 3) -> list[dict]:
    """ticker 기준 최근 DART 공시 문서 텍스트 수집 진입점. 실패 시 빈 리스트 반환."""
    try:
        corp_code = await get_corp_code(ticker)
        if not corp_code:
            return []
        return await _fetch_filing_documents(corp_code, max_count=max_count)
    except Exception as e:
        logger.error("DART 공시 텍스트 수집 예외 (ticker=%s): %s", ticker, e)
        return []
