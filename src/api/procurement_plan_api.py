"""
발주계획현황 + 종합쇼핑몰 납품요구 API 클라이언트

- 발주계획: 수요기관이 등록한 향후 예정 발주 정보 (물품/용역)
- 납품요구: 종합쇼핑몰에서 실제로 발생한 구매 요청 (공고 없는 실거래)

엔드포인트:
    발주계획: https://apis.data.go.kr/1230000/ao/OrderPlanSttusService
    종합쇼핑몰: https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService
"""

import time
from datetime import datetime, timedelta

import requests

from src.config.settings import BASE_URL_PLAN, BASE_URL_SHOP, PROCUREMENT_API_KEY

_HEADERS = {"Accept": "application/json"}
_TIMEOUT = 15
_RETRY = 2


def _get(url: str, params: dict) -> dict:
    params = {"serviceKey": PROCUREMENT_API_KEY, "type": "json", **params}
    for attempt in range(_RETRY):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 403:
                raise PermissionError(f"API 접근 거부 (403) — 승인 대기 중일 수 있습니다: {url}")
        except PermissionError:
            raise
        except Exception:
            if attempt == _RETRY - 1:
                raise
            time.sleep(1)
    return {}


def _extract_items(data: dict) -> list[dict]:
    body = data.get("response", {}).get("body", {})
    items = body.get("items", {})
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        return [items]
    return items if isinstance(items, list) else []


def _total_count(data: dict) -> int:
    return int(data.get("response", {}).get("body", {}).get("totalCount", 0))


# ── 발주계획 ──────────────────────────────────────────────────────────

def get_plan_items(
    start_ym: str,
    end_ym: str,
    page: int = 1,
    rows: int = 100,
) -> tuple[list[dict], int]:
    """
    물품 발주계획 조회.

    Args:
        start_ym: 발주시작년월 (yyyyMM, 예: '202601')
        end_ym:   발주종료년월 (yyyyMM, 예: '202612')
    Returns:
        (items, total_count)
    """
    url = f"{BASE_URL_PLAN}/getOrderPlanSttusListThngPPSSrch"
    params = {
        "pageNo": page, "numOfRows": rows,
        "ordrStrtYm": start_ym, "ordrEndYm": end_ym,
    }
    data = _get(url, params)
    return _extract_items(data), _total_count(data)


def get_plan_services(
    start_ym: str,
    end_ym: str,
    page: int = 1,
    rows: int = 100,
) -> tuple[list[dict], int]:
    """용역 발주계획 조회."""
    url = f"{BASE_URL_PLAN}/getOrderPlanSttusListServcPPSSrch"
    params = {
        "pageNo": page, "numOfRows": rows,
        "ordrStrtYm": start_ym, "ordrEndYm": end_ym,
    }
    data = _get(url, params)
    return _extract_items(data), _total_count(data)


def collect_plan_all(months_ahead: int = 6) -> list[dict]:
    """
    향후 N개월 물품+용역 발주계획 전수 수집.

    Returns:
        발주계획 레코드 리스트 (각 레코드: 발주기관, 품목, 금액 등)
    """
    now = datetime.now()
    start_ym = now.strftime("%Y%m")
    end_dt = now + timedelta(days=30 * months_ahead)
    end_ym = end_dt.strftime("%Y%m")

    records = []
    for fetch_fn in (get_plan_items, get_plan_services):
        page = 1
        while True:
            items, total = fetch_fn(start_ym, end_ym, page=page, rows=100)
            records.extend(items)
            if len(records) >= total or not items:
                break
            page += 1
            time.sleep(0.2)

    return records


# ── 종합쇼핑몰 다수공급자계약 품목 ──────────────────────────────────

def get_mas_products(
    page: int = 1,
    rows: int = 100,
    lrg_clsfc_cd: str | None = None,
) -> tuple[list[dict], int]:
    """
    종합쇼핑몰 다수공급자계약 품목정보 조회 (getMASCntrctPrdctInfoList).

    Args:
        lrg_clsfc_cd: 물품 대분류코드 (None = 전체)
    Returns:
        (items, total_count)
    """
    url = f"{BASE_URL_SHOP}/getMASCntrctPrdctInfoList"
    params: dict = {"pageNo": page, "numOfRows": rows}
    if lrg_clsfc_cd:
        params["prdctLrgclsfcCd"] = lrg_clsfc_cd
    data = _get(url, params)
    return _extract_items(data), _total_count(data)


def collect_mas_products(max_records: int = 5000) -> list[dict]:
    """
    종합쇼핑몰 전체 MAS 계약 품목 수집 (최대 max_records건).

    Returns:
        품목 레코드 리스트 (prdctLrgclsfcNm, prdctMidclsfcNm, cntrctPrceAmt 등 포함)
    """
    records: list[dict] = []
    page = 1
    while len(records) < max_records:
        items, total = get_mas_products(page=page, rows=100)
        records.extend(items)
        if not items or len(records) >= total:
            break
        page += 1
        time.sleep(0.15)
    return records
