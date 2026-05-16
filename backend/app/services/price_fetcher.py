import json
import logging

import httpx

logger = logging.getLogger(__name__)

_URL = "https://polling.finance.naver.com/api/realtime"
_HEADERS = {
    "Referer": "https://finance.naver.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


async def fetch_current_price(ticker: str) -> float | None:
    """네이버 금융 realtime API로 현재주가를 조회한다. 실패 시 None 반환."""
    params = {"query": f"SERVICE_ITEM:{ticker}"}
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=5) as client:
            resp = await client.get(_URL, params=params)
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
        logger.warning("현재주가 조회 실패 (ticker=%s): %s", ticker, e)

    return None
