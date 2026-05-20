"""
조달청 나라장터 계약정보 서비스

역할:
    나라장터 입찰공고와 짝을 이루는 실제 계약 체결 데이터를 수집합니다.
    공고=의사 / 계약=실측 2단 구조에서 "실측" 측 데이터 담당.
    계약금액, 계약체결일, 수요기관, 품명으로 지역별 실수요를 확인합니다.

사용 API:
    조달청 나라장터 계약정보서비스 (data.go.kr 15129427)
    Base URL: https://apis.data.go.kr/1230000/ao/CntrctInfoService
    인증: PROCUREMENT_API_KEY (입찰공고 API와 동일, 별도 활용신청 필요)

지원 엔드포인트 (업무구분별):
    - getCntrctInfoListThngPPSSrch   : 물품 계약 (급식·식자재 등)
    - getCntrctInfoListServcPPSSrch  : 용역 계약 (청소·방역 등)
    - getCntrctInfoListCnstwkPPSSrch : 공사 계약

주요 출력 컬럼:
    ntceNo          - 공고번호 (입찰공고 데이터와 JOIN 키)
    cntrctCnclsDt   - 계약체결일자
    totCntrctAmt    - 총계약금액
    cntrctorNm      - 계약상대자(업체)명
    dminsttNm       - 수요기관명 (지역 식별용)
    prdctClsfcNoNm  - 품명

운영 제약:
    조회기간이 1주일로 축소 운영 중 (응답지연 해소 작업 중).
    collect_contracts_for_district()는 window_days=7 단위로 루프 분할.
    일일 호출 제한: 개발계정 1,000회/일.
"""

from datetime import datetime, timedelta

import pandas as pd
import requests

from src.config.settings import BASE_URL_CONTRACT, PROCUREMENT_API_KEY

# 업무구분별 목록 엔드포인트 (inqryDiv 방식 — PPSSrch는 404 확인)
_CNTRCT_ENDPOINTS: dict[str, str] = {
    "물품": "getCntrctInfoListThng",
    "용역": "getCntrctInfoListServc",
    "공사": "getCntrctInfoListCnstwk",
}


def parse_dminstt_list(raw: str) -> str:
    """
    dminsttList 문자열에서 수요기관명을 추출합니다.
    형식: "[건수^기관코드^기관명^기관유형^부서명^담당자명^전화번호]"
    """
    if not raw or raw == "없음":
        return ""
    try:
        inner = raw.strip("[]")
        parts = inner.split("^")
        return parts[2] if len(parts) > 2 else ""
    except Exception:
        return ""


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


def _default_date_range(days: int = 7) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d0000"), end.strftime("%Y%m%d2359")


def get_contract_list(
    page_no: int = 1,
    num_of_rows: int = 100,
    start_date: str | None = None,
    end_date: str | None = None,
    business_type: str = "물품",
    verbose: bool = False,
) -> pd.DataFrame:
    """
    계약현황 목록을 DataFrame으로 가져옵니다.

    Args:
        business_type: "물품" | "용역" | "공사" 중 하나

    주의:
        조회기간은 7일 이내만 가능 (API 임시 제한).
        수요기관·품목 서버사이드 필터 미지원 → clean_contract_data() 후 로컬 필터링.
        수요기관명은 dminsttList 필드 파싱으로 추출 (parse_dminstt_list() 참조).
    """
    endpoint = _CNTRCT_ENDPOINTS.get(business_type, _CNTRCT_ENDPOINTS["물품"])
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

    url = f"{BASE_URL_CONTRACT}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print(f"[contract_api] 요청 오류: {exc}")
        return pd.DataFrame()

    if resp.status_code != 200:
        if verbose:
            print(f"[contract_api] HTTP {resp.status_code}: {resp.text[:200]}")
        return pd.DataFrame()

    try:
        import json as _json
        data = _json.loads(resp.content.decode("utf-8"))
    except ValueError:
        if verbose:
            print(f"[contract_api] JSON 파싱 실패")
        return pd.DataFrame()

    items = _extract_items(data)
    if not items:
        if verbose:
            rc = data.get("response", {}).get("header", {}).get("resultCode", "?")
            print(f"[contract_api] items 없음 (endpoint={endpoint}, resultCode={rc})")
        return pd.DataFrame()

    if verbose:
        print(f"[contract_api] {len(items)}건 수신 (endpoint={endpoint})")

    df = pd.DataFrame(items)
    df["_source_endpoint"] = endpoint
    df["_business_type"] = business_type
    return df


def collect_contracts_national(
    days_back: int = 30,
    window_days: int = 7,
    pages_per_window: int = 20,
    business_type: str = "물품",
    district_filter: str | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    전국 계약현황을 7일 윈도우로 수집 후 로컬 필터링합니다.

    API 조회기간 1주일 제한 → window_days=7이 기본값.
    서버사이드 지역 필터 미지원 → 수집 후 district_filter로 로컬 필터링.
    수요기관명은 dminsttList 파싱으로 추출합니다.

    Args:
        district_filter: 수요기관명에 포함될 키워드 (예: "부산", "해운대구")
    """
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
            df = get_contract_list(
                page_no=page,
                num_of_rows=100,
                start_date=start_str,
                end_date=end_str,
                business_type=business_type,
                verbose=verbose,
            )
            if df.empty:
                break
            frames.append(df)
            window_count += len(df)
            if len(df) < 100:
                break

        if verbose:
            print(f"  {start_str[:8]}~{end_str[:8]}: {window_count}건")

        cursor = window_end + timedelta(days=1)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["untyCntrctNo"])

    # dminsttList 파싱 → dminsttNm 컬럼 생성
    if "dminsttList" in result.columns:
        result["dminsttNm"] = result["dminsttList"].apply(parse_dminstt_list)

    # 로컬 지역 필터
    if district_filter and "dminsttNm" in result.columns:
        result = result[result["dminsttNm"].str.contains(district_filter, na=False)]

    return result.reset_index(drop=True)


def clean_contract_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    계약현황 원천 데이터를 분석용으로 정제합니다.

    주요 변환:
        - totCntrctAmt(총계약금액), nowCntrctAmt(금차계약금액) → 숫자
        - cntrctCnclsDt(계약체결일) → datetime
    """
    if df.empty:
        return df.copy()

    df = df.copy()

    for col in ["totCntrctAmt", "thtmCntrctAmt"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("원", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 유효 계약금액: totCntrctAmt가 0이면 thtmCntrctAmt(금차) 사용
    if "totCntrctAmt" in df.columns and "thtmCntrctAmt" in df.columns:
        df["cntrctAmt"] = df["totCntrctAmt"].where(df["totCntrctAmt"] > 0, df["thtmCntrctAmt"])

    if "cntrctCnclsDate" in df.columns:
        df["cntrctCnclsDate"] = pd.to_datetime(df["cntrctCnclsDate"], errors="coerce")

    if "_source_district" in df.columns:
        df["district"] = df["_source_district"]
    if "_source_city" in df.columns:
        df["city"] = df["_source_city"]

    return df
