"""
국토부 물류창고업 등록정보 로더

데이터 출처: 공공데이터포털 — 전국 물류창고업 등록정보 (표준데이터셋)
(https://www.data.go.kr/data/15023680/standard.do 또는 유사 데이터셋)

사용 방법:
    1. data.go.kr에서 "물류창고업 등록정보" 파일을 CSV/Excel로 다운로드
    2. data/reference/warehouse_registry.csv 로 저장
    3. load_warehouse_csv() 호출

컬럼 예시 (표준데이터):
    사업체명, 주소, 시도명, 시군구명, 창고동수, 연면적(㎡), 취급품목, 냉동냉장여부, 종업원수
"""

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
REFERENCE_DIR = ROOT / "data" / "reference"
DEFAULT_CSV = REFERENCE_DIR / "warehouse_registry.csv"

# 냉동·냉장 관련 키워드 (식자재·급식 연관 창고 필터용)
COLD_KEYWORDS = ["냉동", "냉장", "저온", "cold", "refriger"]
FOOD_KEYWORDS = ["식품", "식자재", "농산", "수산", "축산", "급식", "냉동", "냉장"]


def load_warehouse_csv(csv_path: Path | str | None = None) -> pd.DataFrame:
    """
    물류창고 등록정보 CSV 로드.

    csv_path: 파일 경로. None이면 data/reference/warehouse_registry.csv 시도.
    파일이 없으면 빈 DataFrame 반환.
    """
    path = Path(csv_path) if csv_path else DEFAULT_CSV
    if not path.exists():
        return pd.DataFrame()

    # 인코딩 자동 감지
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    else:
        return pd.DataFrame()

    return df


def normalize_warehouse(df: pd.DataFrame) -> pd.DataFrame:
    """
    다양한 컬럼명을 통일된 형식으로 변환.
    data.go.kr 표준데이터 기준으로 매핑.
    """
    if df.empty:
        return df.copy()

    col_map = {
        "시도명": "city", "광역시도명": "city",
        "시군구명": "district", "시군구": "district",
        "사업체명": "warehouse_name", "업체명": "warehouse_name",
        "연면적(㎡)": "area_sqm", "연면적": "area_sqm", "면적": "area_sqm",
        "창고동수": "building_count", "동수": "building_count",
        "취급품목": "goods_type", "취급물품": "goods_type",
        "냉동냉장": "cold_storage", "냉동냉장여부": "cold_storage",
        "종업원수": "employee_count",
        "소재지도로명주소": "address", "주소": "address",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    if "area_sqm" in df.columns:
        df["area_sqm"] = pd.to_numeric(
            df["area_sqm"].astype(str).str.replace(",", ""), errors="coerce"
        ).fillna(0)

    if "building_count" in df.columns:
        df["building_count"] = pd.to_numeric(df["building_count"], errors="coerce").fillna(1).astype(int)

    # 냉동냉장 여부 표준화
    if "cold_storage" in df.columns:
        df["is_cold"] = df["cold_storage"].astype(str).str.contains(
            "|".join(COLD_KEYWORDS), case=False, na=False
        )
    elif "goods_type" in df.columns:
        df["is_cold"] = df["goods_type"].astype(str).str.contains(
            "|".join(COLD_KEYWORDS), case=False, na=False
        )
    else:
        df["is_cold"] = False

    # 식품 관련 여부
    goods_col = df.get("goods_type", df.get("warehouse_name", pd.Series([""] * len(df))))
    if isinstance(goods_col, str):
        goods_col = pd.Series([goods_col] * len(df))
    df["is_food_related"] = goods_col.astype(str).str.contains(
        "|".join(FOOD_KEYWORDS), case=False, na=False
    )

    return df
