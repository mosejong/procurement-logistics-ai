import pandas as pd
import requests

from src.config.settings import BASE_URL_POPULATION, POPULATION_API_KEY


def _safe_error_message(exc: requests.RequestException) -> str:
    message = str(exc)
    if POPULATION_API_KEY:
        message = message.replace(POPULATION_API_KEY, "***HIDDEN***")
    return message


def _extract_items(data: dict) -> list[dict]:
    """
    행안부 API 응답에서 실제 item 목록을 최대한 유연하게 꺼냅니다.

    공공데이터포털 API들은 response/body/items/item 구조가 많지만,
    일부는 최상위 키가 다를 수 있어 재귀적으로 item 후보를 찾습니다.
    """
    if not isinstance(data, dict):
        return []

    body = data.get("response", {}).get("body", {})
    items = body.get("items", [])

    if isinstance(items, dict):
        items = items.get("item", items)

    if isinstance(items, list):
        return items

    if isinstance(items, dict):
        return [items]

    for value in data.values():
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            return value

    return []


def get_population_households(
    page_no: int = 1,
    num_of_rows: int = 1000,
    stat_month: str | None = None,
    sido_name: str = "서울특별시",
    sigungu_name: str | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    행정안전부 주민등록 인구 및 세대현황 API를 호출합니다.

    현재 MVP는 서울 자치구 단위 집계를 목표로 하므로 sido_name은 기본값을 서울특별시로 둡니다.
    API 명세/활용계정에 따라 파라미터명이 다를 수 있어 자주 쓰이는 후보명을 함께 보냅니다.
    """
    params = {
        "serviceKey": POPULATION_API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
        "sidoNm": sido_name,
        "ctpvNm": sido_name,
    }

    if stat_month:
        params["srchFrYm"] = stat_month
        params["statsYm"] = stat_month

    if sigungu_name:
        params["sggNm"] = sigungu_name
        params["sigunguNm"] = sigungu_name

    safe_params = params.copy()
    safe_params["serviceKey"] = "***HIDDEN***"

    try:
        response = requests.get(BASE_URL_POPULATION, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print("population request error:", _safe_error_message(exc))
        return pd.DataFrame()

    if verbose:
        print("population_status_code:", response.status_code)
        print("population_endpoint:", BASE_URL_POPULATION)
        print("population_params:", safe_params)
        print("population_response_text:", response.text[:500])

    if response.status_code != 200:
        return pd.DataFrame()

    try:
        data = response.json()
    except ValueError as exc:
        if verbose:
            print("population json parse error:", exc)
        return pd.DataFrame()

    return pd.DataFrame(_extract_items(data))
