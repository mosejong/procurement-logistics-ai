"""
KOSIS Open API — 시도별 시군구 × 산업별 사업체 수·종사자 수

확인된 작동 테이블:
    orgId=210 (경기도), tblId=DT_21002D003
        → 경기도 시군구 × 산업별 사업체수·종사자수 (2022)
        → C1=시군(34개), C2=산업(20개), ITM=T001~T005

API 파라미터 구조 (statisticsParameterData.do):
    method=getList, itmId=ALL, objL1=ALL, objL2=ALL
    prdSe=Y, startPrdDe/endPrdDe=2022

발급: https://kosis.kr → 상단 OPEN API → 사용자 인증키 발급 (무료)
"""

import pandas as pd
import requests

from src.config.settings import KOSIS_API_KEY

BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# 확인된 작동 테이블 목록 (orgId, tblId, 지역)
# 각 시도 통계청이 별도 orgId를 가짐 — 경기도만 실측 확인
REGIONAL_TABLES: list[tuple[str, str, str]] = [
    ("210", "DT_21002D003", "경기도"),
    # 추후 다른 시도 테이블 ID 확인 시 추가:
    # ("211", "DT_21102D003", "서울특별시"),  # 미확인
    # ("212", "DT_21202D003", "부산광역시"),  # 미확인
]

# C2 산업 영문코드 → 우리 품목군 매핑 (ITM_NM_ENG 기준)
INDUSTRY_ENG_TO_CATEGORY: dict[str, str] = {
    "Manufacturing":                                    "IT장비/전산",
    "Information and communications":                  "IT장비/전산",
    "Professional scientific and technical activities":"전문용역/컨설팅",
    "Business facilities managementand business support services": "시설유지보수",
    "Education":                                       "교육물품/교구",
    "Human health and social work activities":         "의료/복지용품",
    "Sewerage waste managementmaterials recovery and remediation activities": "폐기물/환경",
    "Construction":                                    "건설/공사",
    "Transportation":                                  "차량/운송",
    "Wholesale and retail trade":                      "사무용품/소모품",
    "Electricity gas steam and water supply":          "시설유지보수",
}

# C2 코드 → 산업 영문 (API 응답에서 확인된 값)
INDUSTRY_CODE_ENG: dict[str, str] = {
    "001": "Total",
    "002": "Agriculture forestry and fishing",
    "003": "Mining & quarrying",
    "004": "Manufacturing",
    "005": "Electricity gas steam and water supply",
    "006": "Sewerage waste managementmaterials recovery and remediation activities",
    "007": "Construction",
    "008": "Wholesale and retail trade",
    "009": "Transportation",
    "010": "Accommodation and food service activities",
    "011": "Information and communications",
    "012": "Financial and insurance activities",
    "013": "Real estate activites and renting and leasing",
    "014": "Professional scientific and technical activities",
    "015": "Business facilities managementand business support services",
    "016": "Public administration ; compulsory social security",
    "017": "Education",
    "018": "Human health and social work activities",
    "019": "Arts sports and recreation related services",
    "020": "Membership organizations repair and other personal services",
}


def _safe_error(exc: Exception) -> str:
    msg = str(exc)
    if KOSIS_API_KEY:
        msg = msg.replace(KOSIS_API_KEY, "***")
    return msg


def get_business_stats_regional(
    org_id: str = "210",
    tbl_id: str = "DT_21002D003",
    year: str = "2022",
    verbose: bool = False,
) -> pd.DataFrame:
    """
    특정 시도의 시군구별·산업별 사업체·종사자 수를 가져옵니다.

    기본값: 경기도 (orgId=210, tblId=DT_21002D003)

    Returns:
        raw DataFrame — 컬럼: C1, C1_NM, C1_NM_ENG, C2, C2_NM_ENG, ITM_ID, ITM_NM_ENG, DT, PRD_DE
    """
    params = {
        "method": "getList",
        "apiKey": KOSIS_API_KEY,
        "itmId": "ALL",
        "objL1": "ALL",
        "objL2": "ALL",
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "Y",
        "startPrdDe": year,
        "endPrdDe": year,
        "orgId": org_id,
        "tblId": tbl_id,
    }

    if verbose:
        safe = {k: ("***" if k == "apiKey" else v) for k, v in params.items()}
        print(f"KOSIS 요청 orgId={org_id} tblId={tbl_id}:", safe)

    try:
        resp = requests.get(BASE_URL, params=params, timeout=30)
    except requests.RequestException as exc:
        if verbose:
            print("KOSIS 요청 오류:", _safe_error(exc))
        return pd.DataFrame()

    if resp.status_code != 200:
        if verbose:
            print("KOSIS HTTP:", resp.status_code, resp.text[:200])
        return pd.DataFrame()

    try:
        data = resp.json()
    except ValueError as exc:
        if verbose:
            print("KOSIS JSON 파싱 실패:", exc)
        return pd.DataFrame()

    if isinstance(data, dict) and "err" in data:
        if verbose:
            print(f"KOSIS API 오류 (orgId={org_id}): err={data.get('err')} msg={data.get('errMsg','')}")
        return pd.DataFrame()

    if not isinstance(data, list):
        if verbose:
            print("KOSIS 응답 형식 예상 외:", type(data))
        return pd.DataFrame()

    if verbose:
        print(f"KOSIS 응답: {len(data)}행")

    return pd.DataFrame(data)


def _process_regional_df(raw: pd.DataFrame, region_label: str) -> pd.DataFrame:
    """
    raw API 응답 → 정규화된 DataFrame
    [region, district, district_cd, industry_cd, industry_nm, biz_count, emp_count, year]
    """
    if raw.empty:
        return pd.DataFrame()

    # 시도 전체(C1="001" 또는 길이 3) 행 제외 — 시군구 행만 유지
    if "C1" in raw.columns:
        raw = raw[raw["C1"].str.len() > 3].copy()

    # 사업체수 / 종사자수 분리
    biz_raw = raw[raw["ITM_ID"] == "T001"].copy()
    emp_raw = raw[raw["ITM_ID"] == "T003"].copy()

    if biz_raw.empty:
        return pd.DataFrame()

    key_cols = ["C1", "C1_NM", "C2", "C2_NM_ENG", "PRD_DE"]
    key_cols = [c for c in key_cols if c in biz_raw.columns]

    biz_raw["biz_count"] = pd.to_numeric(biz_raw["DT"], errors="coerce").fillna(0).astype(int)
    result = biz_raw[key_cols + ["biz_count"]].copy()

    if not emp_raw.empty:
        emp_raw["emp_count"] = pd.to_numeric(emp_raw["DT"], errors="coerce").fillna(0).astype(int)
        result = result.merge(emp_raw[key_cols + ["emp_count"]], on=key_cols, how="left")
    else:
        result["emp_count"] = 0

    result = result.rename(columns={
        "C1": "district_cd",
        "C1_NM": "district",
        "C2": "industry_cd",
        "C2_NM_ENG": "industry_nm",
        "PRD_DE": "year",
    })

    result["region"] = region_label

    # 산업 → 품목군
    result["item_category"] = result["industry_nm"].map(INDUSTRY_ENG_TO_CATEGORY)

    # 총계(C2=001) 제외
    result = result[result["industry_cd"] != "001"]

    return result


def collect_business_stats(year: str = "2022", verbose: bool = False) -> pd.DataFrame:
    """
    등록된 모든 지역 테이블에서 시군구별·산업별 사업체·종사자 수를 수집합니다.

    Returns:
        DataFrame [region, district, district_cd, industry_cd, industry_nm,
                   biz_count, emp_count, year, item_category]
    """
    frames = []
    for org_id, tbl_id, region in REGIONAL_TABLES:
        raw = get_business_stats_regional(org_id=org_id, tbl_id=tbl_id, year=year, verbose=verbose)
        processed = _process_regional_df(raw, region_label=region)
        if not processed.empty:
            frames.append(processed)
            if verbose:
                print(f"  {region}: {len(processed)}행 처리 완료")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def main() -> None:
    from src.utils.file_handler import ensure_dir, save_csv

    print("KOSIS 지역별 사업체 통계 수집 시작...")
    df = collect_business_stats(verbose=True)

    if df.empty:
        print("수집 결과 없음. API 키와 파라미터를 확인하세요.")
        return

    out = ensure_dir("outputs/tables") / "kosis_business_stats.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out} ({len(df):,}행)")
    print(df.head(10).to_string())
    print(f"\n지역: {df['region'].unique()}")
    print(f"품목군 매핑 완료: {df['item_category'].notna().sum()}/{len(df)}")


if __name__ == "__main__":
    main()
