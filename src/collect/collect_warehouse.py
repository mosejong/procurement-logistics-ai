"""
국토부 물류창고업 등록정보 집계

역할:
    물류창고 등록정보를 시도·자치구 단위로 집계해 logistics_warehouse_summary.csv를 만듭니다.
    기존 수요 기반 hub_score에 창고 인프라 지표를 추가해 "수요 + 인프라" 복합 거점을 제안합니다.

출력: outputs/tables/logistics_warehouse_summary.csv
컬럼: city, warehouse_count, warehouse_area_sum, avg_warehouse_area,
       cold_storage_count, food_related_warehouse_count, logistics_infra_score

준비:
    data.go.kr에서 "물류창고업 등록정보" 파일 다운로드 후
    data/reference/warehouse_registry.csv 로 저장하세요.
    파일 없으면 샘플 데이터로 동작합니다.

실행:
    python -m src.collect.collect_warehouse
"""

from pathlib import Path

import pandas as pd

from src.api.warehouse_api import load_warehouse_csv, normalize_warehouse

ROOT = Path(__file__).parent.parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"
OUT_PATH = TABLES_DIR / "logistics_warehouse_summary.csv"


def _sample_data() -> pd.DataFrame:
    """파일 없을 때 구조 확인용 샘플."""
    rows = [
        {"city": "경기도", "district": "이천시", "warehouse_name": "A물류센터", "area_sqm": 15000, "building_count": 3, "is_cold": True, "is_food_related": True},
        {"city": "경기도", "district": "용인시", "warehouse_name": "B창고", "area_sqm": 8000, "building_count": 2, "is_cold": False, "is_food_related": False},
        {"city": "경기도", "district": "안성시", "warehouse_name": "C저온창고", "area_sqm": 12000, "building_count": 2, "is_cold": True, "is_food_related": True},
        {"city": "부산광역시", "district": "강서구", "warehouse_name": "D허브", "area_sqm": 20000, "building_count": 5, "is_cold": False, "is_food_related": False},
        {"city": "대전광역시", "district": "유성구", "warehouse_name": "E물류", "area_sqm": 9000, "building_count": 2, "is_cold": True, "is_food_related": True},
        {"city": "인천광역시", "district": "중구", "warehouse_name": "F항만창고", "area_sqm": 25000, "building_count": 6, "is_cold": False, "is_food_related": False},
        {"city": "경상북도", "district": "구미시", "warehouse_name": "G창고", "area_sqm": 7000, "building_count": 1, "is_cold": False, "is_food_related": False},
    ]
    return pd.DataFrame(rows)


def _normalize(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(50.0, index=series.index)
    return ((series - mn) / (mx - mn) * 100).round(1)


def run() -> None:
    raw = load_warehouse_csv()

    if raw.empty:
        print("[물류창고] 샘플 모드 (data/reference/warehouse_registry.csv 없음)")
        print("  → data.go.kr '물류창고업 등록정보' 다운로드 후 해당 경로에 저장하면 실데이터로 전환됩니다.")
        df = _sample_data()
    else:
        print(f"[물류창고] CSV 로드: {len(raw)}행")
        df = normalize_warehouse(raw)

    if df.empty or "city" not in df.columns:
        print("[경고] city 컬럼 없음. 컬럼명 확인 필요.")
        return

    # 시도별 집계
    agg_spec: dict = {
        "warehouse_count": ("warehouse_name", "count") if "warehouse_name" in df.columns
                          else ("city", "count"),
    }
    if "area_sqm" in df.columns:
        agg_spec["warehouse_area_sum"] = ("area_sqm", "sum")
        agg_spec["avg_warehouse_area"] = ("area_sqm", "mean")
    if "is_cold" in df.columns:
        agg_spec["cold_storage_count"] = ("is_cold", "sum")
    if "is_food_related" in df.columns:
        agg_spec["food_related_warehouse_count"] = ("is_food_related", "sum")

    summary = df.groupby("city").agg(**agg_spec).reset_index()

    # logistics_infra_score: 창고수(50%) + 면적(30%) + 냉동냉장(20%)
    w_norm = _normalize(summary["warehouse_count"])
    a_norm = _normalize(summary.get("warehouse_area_sum", pd.Series([0] * len(summary))))
    c_norm = _normalize(summary.get("cold_storage_count", pd.Series([0] * len(summary))))

    summary["logistics_infra_score"] = (
        0.5 * w_norm + 0.3 * a_norm + 0.2 * c_norm
    ).round(1)

    for col in ["warehouse_area_sum", "avg_warehouse_area"]:
        if col in summary.columns:
            summary[col] = summary[col].round(0)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] {OUT_PATH.name} ({len(summary)}행)")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    run()
