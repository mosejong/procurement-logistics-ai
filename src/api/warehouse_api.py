"""
국가물류통합정보센터 — 지역별 물류창고업 등록현황 로더

데이터 출처: https://www.nlic.go.kr/nlic/WhsStatsWarehouseLocation.action
자료명: 지역별 물류창고업등록현황 정보 (2026-05-20 기준, 전국 5,911개)

사용 방법:
    1. 위 URL에서 엑셀 다운로드
    2. data/reference/warehouse_location_stats.xls 로 저장 (완료)
    3. load_warehouse_stats() 호출

nlic 파일 컬럼 구조 (고정, header=None 기준):
    col0: 시도
    col1: 합계 (warehouse_count)
    col2: 물류시설법창고 (logistics_facility_law_count)
    col3: 그외창고 (other_warehouse_count)
    col4: 냉동창고 (cold_storage_count)
    col5: 화학류저장창고 (chemical_storage_count)
    col6: 농산물저온창고 (agri_cold_storage_count)
    col7: 축산물냉동창고 (livestock_cold_storage_count)
    col8: 수산식품저온창고 (seafood_cold_storage_count)

food_related_warehouse_count = col4 + col6 + col7 + col8
"""

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
REFERENCE_DIR = ROOT / "data" / "reference"

XLS_PATH  = REFERENCE_DIR / "warehouse_location_stats.xls"
XLSX_PATH = REFERENCE_DIR / "warehouse_location_stats.xlsx"
CSV_PATH  = REFERENCE_DIR / "warehouse_location_stats.csv"

# nlic 파일 고정 컬럼 순서
NLIC_COLS = {
    0: "city",
    1: "warehouse_count",
    2: "logistics_facility_law_count",
    3: "other_warehouse_count",
    4: "cold_storage_count",
    5: "chemical_storage_count",
    6: "agri_cold_storage_count",
    7: "livestock_cold_storage_count",
    8: "seafood_cold_storage_count",
}

TOTAL_ROW_KEYWORDS = ["전국", "합계", "전체", "total", "계"]


def load_warehouse_stats(path: Path | str | None = None) -> pd.DataFrame:
    """nlic xls/xlsx/csv 파일 로드. 파일 없으면 빈 DataFrame."""
    candidates = [Path(path)] if path else [XLS_PATH, XLSX_PATH, CSV_PATH]

    for p in candidates:
        if not p.exists():
            continue
        try:
            if p.suffix in (".xlsx", ".xls"):
                df = pd.read_excel(p, header=None)
            else:
                for enc in ("utf-8-sig", "cp949", "euc-kr"):
                    try:
                        df = pd.read_csv(p, encoding=enc, header=None)
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
    """
    nlic 고정 컬럼 구조로 파싱.
    헤더 3행(타이틀+2단 헤더) 제거 → 전국합계 행 제거 → 숫자 변환 → food_related 계산.
    """
    if df.empty:
        return df.copy()

    df = df.copy()

    # 헤더 행(0~2) 제거, 컬럼명 할당
    df = df.iloc[3:].reset_index(drop=True)
    df = df.rename(columns=NLIC_COLS)

    # 전국 합계 행 제거
    df = df[~df["city"].astype(str).str.strip().isin(TOTAL_ROW_KEYWORDS)].reset_index(drop=True)

    # 숫자 컬럼 변환
    num_cols = [v for v in NLIC_COLS.values() if v != "city"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip(),
                errors="coerce"
            ).fillna(0).astype(int)

    # food_related = 냉동창고 + 농산물저온 + 축산물냉동 + 수산식품저온
    food_cols = [c for c in ["cold_storage_count", "agri_cold_storage_count",
                              "livestock_cold_storage_count", "seafood_cold_storage_count"]
                 if c in df.columns]
    if food_cols:
        df["food_related_warehouse_count"] = df[food_cols].sum(axis=1)

    return df
