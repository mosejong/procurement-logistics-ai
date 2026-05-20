"""
aT 학교급식 계약정보 API

데이터 출처: 공공데이터포털 — aT 학교급식 계약정보
(https://www.data.go.kr/data/1156348/linkedData.do)

API 키 설정: .env의 PUBLIC_DATA_API_KEY (공공데이터 공통 키) 사용
BASE_URL: data.go.kr 포털에서 발급받은 서비스 URL로 settings.py에서 설정

주요 출력 컬럼:
    ctrtNm          - 계약명
    ctrtDate        - 계약일자
    dlvrBgnDate     - 납품시작일자
    dlvrEndDate     - 납품종료일자
    ctrtAmt         - 계약금액
    purchsInsttNm   - 구매사명 (학교)
    purchsInsttSido - 구매사 시도명
    shtNm           - 출하자명 (공급업체)
    shtSido         - 출하자 시도명
"""

import requests
import pandas as pd

from src.config.settings import PUBLIC_DATA_API_KEY, BASE_URL_SCHOOL_MEAL


def get_school_meal_contracts(
    page_no: int = 1,
    num_of_rows: int = 100,
    sido: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    학교급식 계약정보 조회.

    sido: 구매사(학교) 시도명 필터 (예: '부산', '서울')
    start_date / end_date: 계약일자 범위 (YYYYMMDD)
    """
    params = {
        "serviceKey": PUBLIC_DATA_API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
    }
    if sido:
        params["purchsInsttSido"] = sido
    if start_date:
        params["ctrtBgnDate"] = start_date
    if end_date:
        params["ctrtEndDate"] = end_date

    try:
        resp = requests.get(BASE_URL_SCHOOL_MEAL, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print(f"[school_meal_api] 요청 오류: {exc}")
        return pd.DataFrame()

    if resp.status_code != 200:
        if verbose:
            print(f"[school_meal_api] HTTP {resp.status_code}")
        return pd.DataFrame()

    try:
        data = resp.json()
    except ValueError:
        if verbose:
            print("[school_meal_api] JSON 파싱 실패")
        return pd.DataFrame()

    body = data.get("response", {}).get("body", {})
    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not items:
        return pd.DataFrame()

    if verbose:
        print(f"[school_meal_api] {len(items)}건 수신")
    return pd.DataFrame(items)


def clean_school_meal(df: pd.DataFrame) -> pd.DataFrame:
    """학교급식 계약정보 정제."""
    if df.empty:
        return df.copy()

    df = df.copy()
    if "ctrtAmt" in df.columns:
        df["ctrtAmt"] = (
            df["ctrtAmt"].astype(str)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
        df["ctrtAmt"] = pd.to_numeric(df["ctrtAmt"], errors="coerce").fillna(0)

    for col in ["ctrtDate", "dlvrBgnDate", "dlvrEndDate"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df
