"""
국가물류통합정보센터 — 지역별 물류창고업 등록현황 집계

역할:
    nlic.go.kr에서 다운로드한 지역별 물류창고업 통계를 읽어
    시도별 logistics_infra_score를 산출합니다.

    기존 수요 기반 hub_score에 창고 인프라를 더해
    "수요 집중 + 창고 인프라 = 물류 거점" 구조를 완성합니다.

    급식/식자재 시나리오:
        food_related_warehouse_count (식품냉동냉장 + 축산물보관 + 수산냉동냉장)를
        "냉장·냉동 식자재 물류 인프라" 근거로 사용합니다.

출력: outputs/tables/logistics_warehouse_summary.csv
컬럼: city, warehouse_count, logistics_facility_law_count, bonded_warehouse_count,
       chemical_storage_count, food_cold_storage_count, livestock_storage_count,
       seafood_cold_storage_count, food_related_warehouse_count, logistics_infra_score

데이터 준비:
    https://www.nlic.go.kr/nlic/WhsStatsWarehouseLocation.action
    → 엑셀 다운로드 → data/reference/warehouse_location_stats.csv (또는 .xlsx) 저장

실행:
    python -m src.collect.collect_warehouse
"""

from pathlib import Path
import pandas as pd

from src.api.warehouse_api import load_warehouse_stats, normalize_warehouse_stats

ROOT = Path(__file__).parent.parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"
OUT_PATH = TABLES_DIR / "logistics_warehouse_summary.csv"


def _sample_data() -> pd.DataFrame:
    """파일 없을 때 구조 확인용 샘플 (nlic 데이터 구조 반영)."""
    rows = [
        {"city": "서울특별시",     "warehouse_count": 242,  "logistics_facility_law_count": 180, "bonded_warehouse_count": 30, "chemical_storage_count": 5,  "food_cold_storage_count": 18, "livestock_storage_count": 6,  "seafood_cold_storage_count": 3},
        {"city": "경기도",         "warehouse_count": 2254, "logistics_facility_law_count": 1800, "bonded_warehouse_count": 80, "chemical_storage_count": 60, "food_cold_storage_count": 180,"livestock_storage_count": 80, "seafood_cold_storage_count": 54},
        {"city": "인천광역시",     "warehouse_count": 491,  "logistics_facility_law_count": 350, "bonded_warehouse_count": 60, "chemical_storage_count": 15, "food_cold_storage_count": 40, "livestock_storage_count": 15, "seafood_cold_storage_count": 11},
        {"city": "부산광역시",     "warehouse_count": 451,  "logistics_facility_law_count": 320, "bonded_warehouse_count": 50, "chemical_storage_count": 12, "food_cold_storage_count": 38, "livestock_storage_count": 18, "seafood_cold_storage_count": 13},
        {"city": "대구광역시",     "warehouse_count": 198,  "logistics_facility_law_count": 155, "bonded_warehouse_count": 10, "chemical_storage_count": 8,  "food_cold_storage_count": 15, "livestock_storage_count": 7,  "seafood_cold_storage_count": 3},
        {"city": "대전광역시",     "warehouse_count": 176,  "logistics_facility_law_count": 138, "bonded_warehouse_count": 8,  "chemical_storage_count": 7,  "food_cold_storage_count": 13, "livestock_storage_count": 6,  "seafood_cold_storage_count": 4},
        {"city": "광주광역시",     "warehouse_count": 145,  "logistics_facility_law_count": 112, "bonded_warehouse_count": 5,  "chemical_storage_count": 4,  "food_cold_storage_count": 12, "livestock_storage_count": 8,  "seafood_cold_storage_count": 4},
        {"city": "울산광역시",     "warehouse_count": 132,  "logistics_facility_law_count": 100, "bonded_warehouse_count": 15, "chemical_storage_count": 10, "food_cold_storage_count": 5,  "livestock_storage_count": 2,  "seafood_cold_storage_count": 0},
        {"city": "세종특별자치시", "warehouse_count": 45,   "logistics_facility_law_count": 38,  "bonded_warehouse_count": 1,  "chemical_storage_count": 2,  "food_cold_storage_count": 3,  "livestock_storage_count": 1,  "seafood_cold_storage_count": 0},
        {"city": "강원특별자치도", "warehouse_count": 120,  "logistics_facility_law_count": 90,  "bonded_warehouse_count": 3,  "chemical_storage_count": 5,  "food_cold_storage_count": 12, "livestock_storage_count": 7,  "seafood_cold_storage_count": 3},
        {"city": "충청북도",       "warehouse_count": 210,  "logistics_facility_law_count": 165, "bonded_warehouse_count": 5,  "chemical_storage_count": 15, "food_cold_storage_count": 15, "livestock_storage_count": 8,  "seafood_cold_storage_count": 2},
        {"city": "충청남도",       "warehouse_count": 280,  "logistics_facility_law_count": 220, "bonded_warehouse_count": 8,  "chemical_storage_count": 18, "food_cold_storage_count": 20, "livestock_storage_count": 12, "seafood_cold_storage_count": 2},
        {"city": "전라북도",       "warehouse_count": 165,  "logistics_facility_law_count": 128, "bonded_warehouse_count": 3,  "chemical_storage_count": 5,  "food_cold_storage_count": 18, "livestock_storage_count": 8,  "seafood_cold_storage_count": 3},
        {"city": "전라남도",       "warehouse_count": 190,  "logistics_facility_law_count": 145, "bonded_warehouse_count": 5,  "chemical_storage_count": 5,  "food_cold_storage_count": 20, "livestock_storage_count": 12, "seafood_cold_storage_count": 3},
        {"city": "경상북도",       "warehouse_count": 320,  "logistics_facility_law_count": 255, "bonded_warehouse_count": 10, "chemical_storage_count": 20, "food_cold_storage_count": 22, "livestock_storage_count": 10, "seafood_cold_storage_count": 3},
        {"city": "경상남도",       "warehouse_count": 380,  "logistics_facility_law_count": 300, "bonded_warehouse_count": 12, "chemical_storage_count": 18, "food_cold_storage_count": 28, "livestock_storage_count": 14, "seafood_cold_storage_count": 8},
        {"city": "제주특별자치도", "warehouse_count": 112,  "logistics_facility_law_count": 85,  "bonded_warehouse_count": 4,  "chemical_storage_count": 2,  "food_cold_storage_count": 12, "livestock_storage_count": 5,  "seafood_cold_storage_count": 4},
    ]
    df = pd.DataFrame(rows)
    df["food_related_warehouse_count"] = (
        df["food_cold_storage_count"] + df["livestock_storage_count"] + df["seafood_cold_storage_count"]
    )
    return df


def _normalize(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(50.0, index=series.index)
    return ((series - mn) / (mx - mn) * 100).round(1)


def run() -> None:
    raw = load_warehouse_stats()

    if raw.empty:
        print("[물류창고] 샘플 모드 (data/reference/warehouse_location_stats.csv 없음)")
        print("  → https://www.nlic.go.kr/nlic/WhsStatsWarehouseLocation.action")
        print("  → 엑셀 다운로드 후 data/reference/warehouse_location_stats.csv 로 저장하면 실데이터로 전환됩니다.")
        df = _sample_data()
    else:
        print(f"[물류창고] 파일 로드: {len(raw)}행")
        df = normalize_warehouse_stats(raw)

    if df.empty or "city" not in df.columns:
        print("[경고] city 컬럼 없음. 컬럼명 확인 필요.")
        return

    # logistics_infra_score: 전체 창고수(50%) + 식품관련창고(30%) + 물류시설법(20%)
    w_norm  = _normalize(df["warehouse_count"])
    f_norm  = _normalize(df.get("food_related_warehouse_count", pd.Series([0] * len(df))))
    lf_norm = _normalize(df.get("logistics_facility_law_count", pd.Series([0] * len(df))))

    df["logistics_infra_score"] = (
        0.5 * w_norm + 0.3 * f_norm + 0.2 * lf_norm
    ).round(1)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] {OUT_PATH.name} ({len(df)}행)")

    top5 = df.nlargest(5, "logistics_infra_score")[["city", "warehouse_count", "food_related_warehouse_count", "logistics_infra_score"]]
    print("\n[인프라 점수 상위 5개 시도]")
    print(top5.to_string(index=False))


if __name__ == "__main__":
    run()
