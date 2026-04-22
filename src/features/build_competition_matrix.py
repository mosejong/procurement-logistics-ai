"""
자치구별 업종 점포 수 집계 → 경쟁 포화도 매트릭스

소상공인진흥공단 상가정보 API → 업종대분류별 점포 수
→ outputs/tables/seoul_competition_matrix.csv
"""

import logging
import pandas as pd

from src.api.store_api import DISTRICT_SIGNGU_CD, fetch_store_counts
from src.collect.fetch_population_data import load_population_reference
from src.config.settings import OUTPUT_TABLE_DIR
from src.utils.file_handler import ensure_dir, save_csv

logger = logging.getLogger(__name__)

# 업종대분류코드 앞 1자리 → 한글 분류명
INDS_GROUP_MAP: dict[str, str] = {
    "D": "소매",
    "F": "음식/카페",
    "G": "생활서비스",
    "H": "관광/여가",
    "I": "숙박",
    "J": "스포츠",
    "L": "부동산",
    "O": "의료/복지",
    "P": "교육",
    "Q": "수리/개인서비스",
}


def build_competition_matrix(districts: list[str]) -> pd.DataFrame:
    """
    districts 목록의 소상공인 점포 수를 수집해 자치구×업종 매트릭스를 반환합니다.

    Returns:
        DataFrame columns: [district, inds_group, store_count, stores_per_10k]
    """
    frames = []
    pop_ref = load_population_reference().rename(columns={"district_name": "district"})
    pop_map: dict[str, int] = dict(zip(pop_ref["district"], pop_ref["total_population"]))

    for dist in districts:
        logger.info("점포 수집 중: %s", dist)
        df = fetch_store_counts(dist)
        if df.empty:
            logger.warning("데이터 없음: %s", dist)
            continue
        df["inds_group"] = df["inds_lv1_cd"].str[:1].map(INDS_GROUP_MAP).fillna("기타")
        agg = df.groupby(["district", "inds_group"])["store_count"].sum().reset_index()
        frames.append(agg)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    # 인구 보정
    result["population"] = result["district"].map(pop_map).fillna(0).astype(int)
    result["stores_per_10k"] = result.apply(
        lambda r: round(r["store_count"] / (r["population"] / 10_000), 2)
        if r["population"] > 0 else 0.0,
        axis=1,
    )

    return result


def main(districts: list[str] | None = None) -> None:
    from src.features.build_opportunity_matrix import TARGET_DISTRICTS

    if districts is None:
        districts = TARGET_DISTRICTS

    ensure_dir(OUTPUT_TABLE_DIR)
    matrix = build_competition_matrix(districts)
    if matrix.empty:
        print("수집된 데이터 없음")
        return

    path = save_csv(matrix, f"{OUTPUT_TABLE_DIR}/seoul_competition_matrix.csv")
    print(f"경쟁 매트릭스 저장: {path}")
    print(matrix.to_string())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()