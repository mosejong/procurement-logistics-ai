"""
조달청 나라장터 낙찰결과 / 계약정보 API

역할:
    입찰공고와 짝을 이루는 낙찰 결과 데이터를 수집합니다.
    낙찰업체명, 낙찰금액, 낙찰일, 공고번호를 가져와 입찰공고 데이터와 JOIN합니다.

사용 API:
    조달청 나라장터 개방API 2.0 — BidPublicInfoService
    서비스키: PROCUREMENT_API_KEY (입찰공고 API와 동일)

지원 엔드포인트 (자동 폴백):
    1. getBidPblancListInfoBidResultSrch      - 입찰결과목록 (서비스/물품 통합)
    2. getBidResultListInfoServcPPSSrch        - 서비스분야 입찰결과
    3. getBidResultListInfoThngPPSSrch         - 물품분야 입찰결과

주요 출력 컬럼:
    bidNtceNo       - 입찰공고번호 (입찰공고 데이터와 JOIN 키)
    sucsfbidNm      - 낙찰업체명
    sucsfbidAmt     - 낙찰금액
    opengDt         - 개찰일시
    dminsttNm       - 수요기관명
    bdgtAmt         - 배정예산
    drwtPcnt        - 낙찰률(낙찰금액/예정가격)
"""

from datetime import datetime, timedelta

import pandas as pd
import requests

from src.config.settings import BASE_URL_BID, PROCUREMENT_API_KEY

# 시도 순서대로 시도할 엔드포인트 목록
_RESULT_ENDPOINTS = [
    "getBidPblancListInfoBidResultSrch",
    "getBidResultListInfoServcPPSSrch",
    "getBidResultListInfoThngPPSSrch",
]


def _extract_items(data: dict) -> list[dict]:
    body = data.get("response", {}).get("body", {})
    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return items
    return []


def _default_date_range(days: int = 30) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d0000"), end.strftime("%Y%m%d2359")


def get_award_list(
    page_no: int = 1,
    num_of_rows: int = 100,
    start_date: str | None = None,
    end_date: str | None = None,
    dminstt_nm: str | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    낙찰결과 목록을 DataFrame으로 가져옵니다.

    엔드포인트를 순서대로 시도하고 데이터가 있으면 바로 반환합니다.
    dminstt_nm 으로 수요기관명을 필터링할 수 있습니다.
    """
    default_start, default_end = _default_date_range()
    params = {
        "serviceKey": PROCUREMENT_API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "inqryDiv": "1",
        "inqryBgnDt": start_date or default_start,
        "inqryEndDt": end_date or default_end,
        "type": "json",
    }
    if dminstt_nm:
        params["dminsttNm"] = dminstt_nm

    for endpoint_name in _RESULT_ENDPOINTS:
        url = f"{BASE_URL_BID}/{endpoint_name}"
        try:
            resp = requests.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            if verbose:
                print(f"[{endpoint_name}] 요청 오류: {exc}")
            continue

        if resp.status_code != 200:
            if verbose:
                print(f"[{endpoint_name}] HTTP {resp.status_code}")
            continue

        try:
            data = resp.json()
        except ValueError:
            if verbose:
                print(f"[{endpoint_name}] JSON 파싱 실패")
            continue

        items = _extract_items(data)
        if not items:
            if verbose:
                print(f"[{endpoint_name}] items 없음")
            continue

        if verbose:
            print(f"[{endpoint_name}] {len(items)}건 수신")
        df = pd.DataFrame(items)
        df["_source_endpoint"] = endpoint_name
        return df

    return pd.DataFrame()


def collect_awards_for_district(
    city: str,
    district: str,
    days_back: int = 730,
    window_days: int = 30,
    pages_per_window: int = 5,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    특정 지역의 낙찰결과를 기간 단위로 수집합니다.
    city, district 태그를 붙여 반환합니다.
    """
    from datetime import timedelta

    end = datetime.now()
    start = end - timedelta(days=days_back)
    frames = []

    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=window_days), end)
        start_str = cursor.strftime("%Y%m%d0000")
        end_str = window_end.strftime("%Y%m%d2359")

        window_count = 0
        for page in range(1, pages_per_window + 1):
            df = get_award_list(
                page_no=page,
                num_of_rows=100,
                start_date=start_str,
                end_date=end_str,
                dminstt_nm=district,
                verbose=verbose,
            )
            if df.empty:
                break
            frames.append(df)
            window_count += len(df)

        if window_count and verbose:
            print(f"  {start_str[:8]}~{end_str[:8]}: {window_count}건")

        cursor = window_end + timedelta(days=1)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True).drop_duplicates()
    result["_source_city"] = city
    result["_source_district"] = district
    return result


def clean_award_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    낙찰결과 원천 데이터를 분석용으로 정제합니다.

    주요 변환:
        - sucsfbidAmt(낙찰금액), bdgtAmt(배정예산) → 숫자
        - opengDt(개찰일) → datetime
        - drwtPcnt(낙찰률) → float, 없으면 낙찰금액/예산으로 계산
    """
    if df.empty:
        return df.copy()

    df = df.copy()

    for col in ["sucsfbidAmt", "bdgtAmt", "presmptPrce"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("원", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "opengDt" in df.columns:
        df["opengDt"] = pd.to_datetime(df["opengDt"], errors="coerce")

    # 낙찰률 계산: sucsfbidAmt / presmptPrce (예정가격 기준)
    if "drwtPcnt" not in df.columns or df["drwtPcnt"].isna().all():
        base_col = "presmptPrce" if "presmptPrce" in df.columns else "bdgtAmt"
        if base_col in df.columns:
            df["drwtPcnt"] = (
                df["sucsfbidAmt"] / df[base_col].replace(0, float("nan")) * 100
            ).round(2)

    # 지역 컬럼 정규화
    if "_source_district" in df.columns:
        df["district"] = df["_source_district"]
    if "_source_city" in df.columns:
        df["city"] = df["_source_city"]

    return df
