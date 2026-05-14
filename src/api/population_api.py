import pandas as pd
import requests

from src.config.settings import BASE_URL_POPULATION, POPULATION_API_KEY

# ── 시군구 단위 인구 API (data.go.kr 15108071) ──────────────────────────────
# 행안부_법정동별(행정동 통반단위) 주민등록 인구 및 세대현황
# lv=2: 시군구 단위, stdgCd: 시도 법정동코드(10자리)
BASE_URL_SGG_POPULATION = (
    "https://apis.data.go.kr/1741000/stdgPpltnHhStus/selectStdgPpltnHhStus"
)

# 시도별 법정동코드 10자리 (시도코드(2) + 00000000)
SIDO_STDG_CODES: dict[str, str] = {
    "서울특별시":     "1100000000",
    "부산광역시":     "2600000000",
    "대구광역시":     "2700000000",
    "인천광역시":     "2800000000",
    "광주광역시":     "2900000000",
    "대전광역시":     "3000000000",
    "울산광역시":     "3100000000",
    "세종특별자치시": "3600000000",
    "경기도":         "4100000000",
    "강원특별자치도": "5100000000",  # 2023년 특별자치도 전환 후 코드 변경
    "충청북도":       "4300000000",
    "충청남도":       "4400000000",
    "전북특별자치도": "5200000000",  # 2024년 특별자치도 전환 후 코드 변경
    "전라남도":       "4600000000",
    "경상북도":       "4700000000",
    "경상남도":       "4800000000",
    "제주특별자치도": "5000000000",
}

# ── 시도 단위 인구 API (data.go.kr 15107303) ───────────────────────────────
# 행정안전부_통계연보_지역별 주민등록인구 — ServiceKey(대문자) 파라미터
BASE_URL_SIDO_POPULATION = (
    "https://apis.data.go.kr/1741000/RegistrationPopulationByRegion"
    "/getRegistrationPopulationByRegion"
)

# seq(고정 순서) → 프로젝트 city 명칭 매핑
# API가 시도명을 축약형으로 반환해 seq 기반 매핑이 더 안전함
SIDO_SEQ_MAP: dict[int, str] = {
    1:  "전국",
    2:  "서울특별시",
    3:  "부산광역시",
    4:  "대구광역시",
    5:  "인천광역시",
    6:  "광주광역시",
    7:  "대전광역시",
    8:  "울산광역시",
    9:  "세종특별자치시",
    10: "경기도",
    11: "강원특별자치도",
    12: "충청북도",
    13: "충청남도",
    14: "전북특별자치도",
    15: "전라남도",
    16: "경상북도",
    17: "경상남도",
    18: "제주특별자치도",
}


def _safe_error_message(exc: requests.RequestException) -> str:
    message = str(exc)
    if POPULATION_API_KEY:
        message = message.replace(POPULATION_API_KEY, "***HIDDEN***")
    return message


def get_district_population(
    city: str,
    ym: str = "202501",
    verbose: bool = False,
) -> pd.DataFrame:
    """
    행안부 법정동별 인구 API (15108071) — 시군구 단위 인구를 반환합니다.

    Args:
        city: 시도명 (예: "서울특별시", "경기도")
        ym:   기준 년월 YYYYMM (2022-10 이후)

    Returns:
        DataFrame [city, district, total_population, male_population,
                   female_population, households, stats_ym]
    """
    stdg_cd = SIDO_STDG_CODES.get(city)
    if not stdg_cd:
        if verbose:
            print(f"[인구] 법정동코드 없음: {city}")
        return pd.DataFrame()

    params = {
        "serviceKey": POPULATION_API_KEY,
        "stdgCd": stdg_cd,
        "srchFrYm": ym,
        "srchToYm": ym,
        "lv": "2",        # 시군구 단위
        "type": "json",
        "numOfRows": "100",
        "pageNo": "1",
    }

    try:
        resp = requests.get(BASE_URL_SGG_POPULATION, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print(f"[인구] 요청 오류 ({city}):", _safe_error_message(exc))
        return pd.DataFrame()

    if resp.status_code != 200:
        if verbose:
            print(f"[인구] HTTP {resp.status_code} ({city})")
        return pd.DataFrame()

    try:
        data = resp.json()
    except ValueError:
        return pd.DataFrame()

    # 응답 구조: Response.head / Response.items.item
    head = data.get("Response", {}).get("head", {})
    result_code = head.get("resultCode", "?")
    if result_code not in ("0", 0):
        if verbose:
            print(f"[인구] API 오류 ({city}): code={result_code} msg={head.get('resultMsg','')}")
        return pd.DataFrame()

    items = data.get("Response", {}).get("items", {})
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)

    # 컬럼 정규화
    df = df.rename(columns={
        "ctpvNm": "city_raw",
        "sggNm":  "district",
        "totNmprCnt": "total_population",
        "maleNmprCnt": "male_population",
        "femlNmprCnt": "female_population",
        "hhCnt": "households",
        "statsYm": "stats_ym",
    })

    for col in ["total_population", "male_population", "female_population", "households"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["city"] = city

    cols = ["city", "district", "total_population", "male_population",
            "female_population", "households", "stats_ym"]
    return df[[c for c in cols if c in df.columns]]


def get_sido_population(year: str | None = None, verbose: bool = False) -> pd.DataFrame:
    """
    행안부 통계연보 — 전국 17개 시도 단위 주민등록인구를 가져옵니다.
    (data.go.kr API 15107303, ServiceKey 대문자 파라미터)

    Args:
        year: 연도 4자리 문자열 (예: "2024"). None이면 최신 연도.

    Returns:
        DataFrame [city, population_tot, houshol, year]
    """
    params = {
        "ServiceKey": POPULATION_API_KEY,
        "pageNo": "1",
        "numOfRows": "1000",
        "type": "json",
    }

    try:
        resp = requests.get(BASE_URL_SIDO_POPULATION, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print("sido population 요청 오류:", _safe_error_message(exc))
        return pd.DataFrame()

    if resp.status_code != 200:
        if verbose:
            print("sido population HTTP:", resp.status_code)
        return pd.DataFrame()

    try:
        data = resp.json()
    except ValueError:
        return pd.DataFrame()

    outer = data.get("RegistrationPopulationByRegion", [])
    rows = outer[1].get("row", []) if len(outer) > 1 else []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # 최신 연도 필터
    target_year = year or df["wrttimeid"].max()
    df = df[df["wrttimeid"] == target_year].copy()

    # seq → city 매핑 (regi 축약형 대신 고정 순서로 매핑)
    df["seq"] = pd.to_numeric(df["seq"], errors="coerce")
    df["city"] = df["seq"].map(SIDO_SEQ_MAP)
    df = df.rename(columns={"wrttimeid": "year"})

    numeric_cols = ["population_tot", "population_man", "population_female", "houshol"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df[["city", "population_tot", "population_man", "population_female", "houshol", "year"]].dropna(subset=["city"])


def get_population_households(
    page_no: int = 1,
    num_of_rows: int = 1000,
    stat_month: str | None = None,
    sido_name: str = "서울특별시",
    sigungu_name: str | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    (레거시) 행정안전부 주민등록 인구 및 세대현황 API.
    현재는 err=11로 실패 — get_sido_population() 사용 권장.
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

    try:
        response = requests.get(BASE_URL_POPULATION, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print("population request error:", _safe_error_message(exc))
        return pd.DataFrame()

    if response.status_code != 200:
        return pd.DataFrame()

    try:
        data = response.json()
    except ValueError:
        return pd.DataFrame()

    # 새 응답 구조 (RegistrationPopulationByRegion)
    if "RegistrationPopulationByRegion" in data:
        outer = data["RegistrationPopulationByRegion"]
        rows = outer[1].get("row", []) if len(outer) > 1 else []
        return pd.DataFrame(rows)

    # 구형 응답 구조
    body = data.get("response", {}).get("body", {})
    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return pd.DataFrame(items) if isinstance(items, list) else pd.DataFrame()
