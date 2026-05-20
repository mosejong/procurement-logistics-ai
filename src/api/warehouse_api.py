"""
국가물류통합정보센터 — 지역별 물류창고업 등록현황 로더

데이터 출처: https://www.nlic.go.kr/nlic/WhsStatsWarehouseLocation.action
자료명: 지역별 물류창고업등록현황 정보

사용 방법:
    1. 위 URL에서 엑셀 다운로드
    2. data/reference/warehouse_location_stats.csv (또는 .xlsx) 로 저장
    3. load_warehouse_stats() 호출

제공 데이터 (시도 단위 집계):
    - 전체 창고 수 (2026 기준 전국 5,911건)
    - 물류시설법, 보세창고, 화학류저장
    - 식품위생법 냉동냉장, 축산물위생법 축산물보관, 수산식품산업법 냉동냉장
    → food_related_warehouse_count = 식품냉동냉장 + 축산물보관 + 수산냉동냉장
"""

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
REFERENCE_DIR = ROOT / "data" / "reference"

CSV_PATH = REFERENCE_DIR / "warehouse_location_stats.csv"
XLSX_PATH = REFERENCE_DIR / "warehouse_location_stats.xlsx"

# 다운로드 파일 컬럼명 → 통일 컬럼명 매핑
COL_MAP = {
    "시도": "city", "시·도": "city", "지역": "city",
    "합계": "warehouse_count", "전체": "warehouse_count", "총계": "warehouse_count",
    "물류시설법": "logistics_facility_law_count",
    "보세창고": "bonded_warehouse_count",
    "화학류저장": "chemical_storage_count",
    "식품위생법": "food_cold_storage_count",
    "식품위생법냉동냉장": "food_cold_storage_count",
    "식품위생법 냉동냉장": "food_cold_storage_count",
    "축산물위생법": "livestock_storage_count",
    "축산물위생법축산물보관": "livestock_storage_count",
    "축산물위생법 축산물보관": "livestock_storage_count",
    "수산식품산업법": "seafood_cold_storage_count",
    "수산식품산업법냉동냉장": "seafood_cold_storage_count",
    "수산식품산업법 냉동냉장": "seafood_cold_storage_count",
}

# 전국 합계 행 제외 키워드
TOTAL_ROW_KEYWORDS = ["전국", "합계", "전체", "total", "계"]


def load_warehouse_stats(path: Path | str | None = None) -> pd.DataFrame:
    """
    지역별 물류창고업 등록현황 파일 로드.
    CSV 또는 Excel 모두 지원. 파일 없으면 빈 DataFrame 반환.
    """
    candidates = [Path(path)] if path else [CSV_PATH, XLSX_PATH]

    for p in candidates:
        if not p.exists():
            continue
        try:
            if p.suffix in (".xlsx", ".xls"):
                df = pd.read_excel(p, header=0)
            else:
                for enc in ("utf-8-sig", "cp949", "euc-kr"):
                    try:
                        df = pd.read_csv(p, encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    continue
            return df
        except Exception:
            continue

    return pd.DataFrame()


def normalize_warehouse_stats(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명 통일 + 파생 지표 계산."""
    if df.empty:
        return df.copy()

    df = df.copy()

    # 컬럼명 정규화 (공백 제거 후 매핑)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})

    # 전국 합계 행 제거
    if "city" in df.columns:
        mask = df["city"].astype(str).str.strip().isin(TOTAL_ROW_KEYWORDS)
        df = df[~mask].reset_index(drop=True)

    # 숫자 컬럼 정수 변환
    num_cols = [
        "warehouse_count", "logistics_facility_law_count", "bonded_warehouse_count",
        "chemical_storage_count", "food_cold_storage_count",
        "livestock_storage_count", "seafood_cold_storage_count",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip(),
                errors="coerce"
            ).fillna(0).astype(int)

    # food_related_warehouse_count = 식품냉동냉장 + 축산물보관 + 수산냉동냉장
    food_cols = [c for c in ["food_cold_storage_count", "livestock_storage_count", "seafood_cold_storage_count"] if c in df.columns]
    if food_cols:
        df["food_related_warehouse_count"] = df[food_cols].sum(axis=1)

    return df
