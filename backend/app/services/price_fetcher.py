import json
import logging

import httpx

logger = logging.getLogger(__name__)

_MOBILE_URL = "https://m.stock.naver.com/api/stock/{ticker}/basic"
_POLLING_URL = "https://polling.finance.naver.com/api/realtime"
_HEADERS = {
    "Referer": "https://finance.naver.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


async def fetch_current_price(ticker: str) -> float | None:
    """현재주가를 조회한다. 네이버 모바일 API를 우선 시도하고 실패 시 폴링 API로 폴백한다."""
    logger.info("[price] 주가 조회 시작 (ticker=%s)", ticker)

    price = await _fetch_from_mobile_api(ticker)
    if price is not None:
        logger.info("[price] 모바일 API 성공 (ticker=%s, price=%s)", ticker, price)
        return price

    logger.warning("[price] 모바일 API None 반환, 폴링 API로 폴백 (ticker=%s)", ticker)
    price = await _fetch_from_polling_api(ticker)
    if price is not None:
        logger.info("[price] 폴링 API 성공 (ticker=%s, price=%s)", ticker, price)
    else:
        logger.warning("[price] 두 API 모두 실패 (ticker=%s)", ticker)
    return price


async def _fetch_from_mobile_api(ticker: str) -> float | None:
    """네이버 모바일 주식 API에서 현재주가 조회."""
    url = _MOBILE_URL.format(ticker=ticker)
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=8) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        price_str = data.get("closePrice") or data.get("stockPrice")
        if price_str is not None:
            return float(str(price_str).replace(",", ""))
    except Exception as e:
        logger.warning("모바일 API 주가 조회 실패 (ticker=%s): %s", ticker, e)

    return None


async def _fetch_from_polling_api(ticker: str) -> float | None:
    """네이버 금융 realtime 폴링 API에서 현재주가 조회."""
    params = {"query": f"SERVICE_ITEM:{ticker}"}
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=8) as client:
            resp = await client.get(_POLLING_URL, params=params)
            resp.raise_for_status()

        data = json.loads(resp.content.decode("euc-kr", errors="replace"))

        areas = data.get("result", {}).get("areas", [])
        for area in areas:
            if area.get("name") == "SERVICE_ITEM":
                datas = area.get("datas", [])
                if datas:
                    nv = datas[0].get("nv")
                    if nv is not None:
                        return float(nv)
    except Exception as e:
        logger.warning("폴링 API 주가 조회 실패 (ticker=%s): %s", ticker, e)

    return None
