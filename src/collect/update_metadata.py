"""
metadata.json 갱신 스크립트

수집 후 실행하면 data/processed/metadata.json을 실측값으로 업데이트합니다.
build_national_sample.py가 suffix='national'일 때 자동 호출됩니다.
배치 수집 후에는 수동으로 실행: python -m src.collect.update_metadata
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
TABLES_DIR = ROOT / "outputs" / "tables"
METADATA_PATH = PROCESSED_DIR / "metadata.json"


def update_metadata() -> dict:
    meta: dict = {}

    # 기존 값 로드 (부분 업데이트 지원)
    if METADATA_PATH.exists():
        try:
            meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    import pandas as pd

    # 1. 총 공고수: map_item_city_summary.csv bid_count 합계
    #    (전국 지도 탭이 같은 파일을 사용하므로 숫자 일치)
    map_path = TABLES_DIR / "map_item_city_summary.csv"
    if map_path.exists():
        s = pd.read_csv(map_path, encoding="utf-8-sig", usecols=lambda c: c == "bid_count")
        if "bid_count" in s.columns:
            meta["total_bids"] = int(s["bid_count"].sum())
            print(f"  total_bids: {meta['total_bids']:,}")
    else:
        print(f"  [skip] {map_path.name} 없음 — total_bids 유지")

    # 2. 시도·시군구·품목군: opportunity_matrix_national.csv 기준
    matrix_path = TABLES_DIR / "opportunity_matrix_national.csv"
    if matrix_path.exists():
        m = pd.read_csv(matrix_path, encoding="utf-8-sig", usecols=lambda c: c in ("city", "district", "item_category"))
        if "city" in m.columns:
            meta["cities"] = int(m["city"].nunique())
            print(f"  cities: {meta['cities']}")
        if "district" in m.columns:
            meta["districts"] = int(m["district"].nunique())
            print(f"  districts: {meta['districts']}")
        if "item_category" in m.columns:
            meta["item_categories"] = int(m["item_category"].nunique())
            print(f"  item_categories: {meta['item_categories']}")
    else:
        print(f"  [skip] {matrix_path.name} 없음 — 기존 값 유지")

    meta["api_sources"] = 4

    from datetime import datetime
    meta["updated_at"] = datetime.now().strftime("%Y-%m-%d")

    METADATA_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] metadata.json 갱신 완료: {METADATA_PATH}")
    return meta


if __name__ == "__main__":
    update_metadata()
