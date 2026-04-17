import requests
import pandas as pd
from src.config.settings import PROCUREMENT_API_KEY, BASE_URL_BID


def get_bid_list(page_no=1, num_of_rows=5):
    endpoint = f"{BASE_URL_BID}/getBidPblancListInfoServcPPSSrch"

    params = {
        "serviceKey": PROCUREMENT_API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }

    safe_params = params.copy()
    safe_params["serviceKey"] = "***HIDDEN***"

    response = requests.get(endpoint, params=params, timeout=30)

    print("status_code:", response.status_code)
    print("endpoint:", endpoint)
    print("params:", safe_params)
    print("response_text:", response.text[:500])

    if response.status_code != 200:
        return pd.DataFrame()

    try:
        data = response.json()
        print("response_json_keys:", data.keys())

        body = data.get("response", {}).get("body", {})
        items = body.get("items", [])

        if isinstance(items, dict):
            if "item" in items:
                items = items["item"]
            else:
                items = [items]

        if isinstance(items, dict):
            items = [items]

        return pd.DataFrame(items)
    except Exception as e:
        print("json parse error:", e)
        return pd.DataFrame()