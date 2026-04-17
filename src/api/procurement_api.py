import requests
import pandas as pd
from src.config.settings import PROCUREMENT_API_KEY, BASE_URL_BID


def get_bid_list(page_no=1, num_of_rows=10, start_date=None, end_date=None):
    """
    나라장터 입찰공고 목록 조회용 기본 함수
    실제 사용할 오퍼레이션명은 공공데이터포털 문서 보고 맞춰주면 됨
    """

    endpoint = f"{BASE_URL_BID}/getBidPblancListInfoServcPPSSrch"

    params = {
        "serviceKey": PROCUREMENT_API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }

    if start_date:
        params["inqryDiv"] = "1"
        params["inqryBgnDt"] = start_date
    if end_date:
        params["inqryEndDt"] = end_date

    response = requests.get(endpoint, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    try:
        items = data["response"]["body"]["items"]
        if isinstance(items, dict):
            items = [items]
        return pd.DataFrame(items)
    except Exception:
        print("응답 구조 확인 필요:")
        print(data)
        return pd.DataFrame()