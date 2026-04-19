from datetime import datetime, timedelta

import pandas as pd
import requests

from src.config.settings import BASE_URL_BID, PROCUREMENT_API_KEY


def _extract_items(data: dict) -> list[dict]:
    """공공데이터 API 응답에서 실제 공고 목록(items)을 꺼냅니다."""
    body = data.get("response", {}).get("body", {})
    items = body.get("items", [])

    if isinstance(items, dict):
        items = items.get("item", items)

    if isinstance(items, dict):
        return [items]

    if isinstance(items, list):
        return items

    return []


def _safe_error_message(exc: requests.RequestException) -> str:
    """에러 메시지에 API 키가 섞여 나오지 않도록 숨깁니다."""
    message = str(exc)
    if PROCUREMENT_API_KEY:
        message = message.replace(PROCUREMENT_API_KEY, "***HIDDEN***")
    return message


def _default_date_range(days: int = 30) -> tuple[str, str]:
    """조회 기간을 따로 안 넣었을 때 최근 N일로 검색합니다."""
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d0000"), end.strftime("%Y%m%d2359")


def _print_api_error(data: dict) -> None:
    """공공데이터 API가 내려주는 resultCode/resultMsg를 디버깅용으로 출력합니다."""
    error = data.get("nkoneps.com.response.ResponseError")
    if not isinstance(error, dict):
        return

    header = error.get("header", {})
    print("api_result_code:", header.get("resultCode"))
    print("api_result_msg:", header.get("resultMsg"))


def get_bid_list(
    page_no: int = 1,
    num_of_rows: int = 5,
    keyword: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    extra_params: dict | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    조달청 나라장터 입찰공고 목록을 DataFrame으로 가져옵니다.

    build_seoul_sample.py와 test_api.py가 이 함수를 사용합니다.
    """
    endpoint = f"{BASE_URL_BID}/getBidPblancListInfoServcPPSSrch"
    default_start, default_end = _default_date_range()
    params = {
        "serviceKey": PROCUREMENT_API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        # 이 API는 조회구분과 기간이 없으면 필수값 오류가 나서 기본값을 넣습니다.
        "inqryDiv": "1",
        "inqryBgnDt": start_date or default_start,
        "inqryEndDt": end_date or default_end,
        "type": "json",
    }

    if keyword:
        params["bidNtceNm"] = keyword

    if extra_params:
        # 나중에 수요기관명, 업무구분 같은 추가 검색조건을 실험할 때 쓰는 자리입니다.
        params.update(extra_params)

    safe_params = params.copy()
    safe_params["serviceKey"] = "***HIDDEN***"

    try:
        response = requests.get(endpoint, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print("request error:", _safe_error_message(exc))
        return pd.DataFrame()

    if verbose:
        # verbose=True일 때만 요청/응답 일부를 보여줘서 API 디버깅을 쉽게 합니다.
        print("status_code:", response.status_code)
        print("endpoint:", endpoint)
        print("params:", safe_params)
        print("response_text:", response.text[:500])

    if response.status_code != 200:
        return pd.DataFrame()

    try:
        data = response.json()
    except ValueError as exc:
        if verbose:
            print("json parse error:", exc)
        return pd.DataFrame()

    if verbose:
        print("response_json_keys:", data.keys())
        _print_api_error(data)

    return pd.DataFrame(_extract_items(data))
