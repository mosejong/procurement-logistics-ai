"""
전국 자치구별 소상공인 점포 수 집계 → 경쟁 포화도 매트릭스

소상공인진흥공단 상가정보 API → 업종대분류별 점포 수
→ outputs/tables/national_competition_matrix.csv

컬럼: [city, district, inds_group, store_count, population, stores_per_10k]
"""

import logging
import pandas as pd
from pathlib import Path

from src.api.store_api import fetch_store_counts, API_UNSUPPORTED_CITIES, AGGREGATE_CITY_CODES, _lookup_signgu_cd
from src.config.settings import OUTPUT_TABLE_DIR
from src.utils.file_handler import ensure_dir, save_csv

logger = logging.getLogger(__name__)

NATIONAL_POP_PATH = Path("data/reference/national_district_population.csv")

INDS_GROUP_MAP: dict[str, str] = {
    "G2": "소매",
    "I1": "숙박",
    "I2": "음식/카페",
    "L1": "부동산",
    "N1": "생활서비스",
    "P1": "교육",
    "Q1": "의료/복지",
    "R1": "관광/여가",
    "S2": "수리/개인서비스",
}


def load_population_map() -> dict[tuple[str, str], int]:
    """(city, district) → total_population 매핑을 반환합니다."""
    if not NATIONAL_POP_PATH.exists():
        return {}
    df = pd.read_csv(NATIONAL_POP_PATH, encoding="utf-8-sig")
    return {(row["city"], row["district"]): int(row["total_population"])
            for _, row in df.iterrows()}


def build_competition_matrix(
    districts: list[tuple[str, str]],
    pop_map: dict[tuple[str, str], int] | None = None,
) -> pd.DataFrame:
    """
    (city, district) 목록의 소상공인 점포 수를 수집해 경쟁 포화도 매트릭스를 반환합니다.

    Args:
        districts: [(city, district), ...] 수집 대상
        pop_map:   (city, district) → population 매핑. None이면 자동 로드.

    Returns:
        DataFrame [city, district, inds_group, store_count, population, stores_per_10k]
    """
    if pop_map is None:
        pop_map = load_population_map()

    frames = []
    for city, district in districts:
        if city in API_UNSUPPORTED_CITIES:
            logger.debug("API 미지원 시/도 스킵: %s", city)
            continue
        cd = _lookup_signgu_cd(city, district)
        if not cd:
            logger.debug("시군구코드 없음 스킵: %s %s", city, district)
            continue

        logger.info("점포 수집 중: %s %s (%s)", city, district, cd)
        df = fetch_store_counts(district, city=city)
        if df.empty:
            logger.warning("데이터 없음: %s %s", city, district)
            continue

        df["inds_group"] = df["inds_lv1_cd"].map(INDS_GROUP_MAP).fillna("기타")
        agg = df.groupby(["city", "district", "inds_group"])["store_count"].sum().reset_index()
        frames.append(agg)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    result["population"] = result.apply(
        lambda r: pop_map.get((r["city"], r["district"]), 0), axis=1
    ).astype(int)
    result["stores_per_10k"] = result.apply(
        lambda r: round(r["store_count"] / (r["population"] / 10_000), 2)
        if r["population"] > 0 else 0.0,
        axis=1,
    )

    return result.sort_values(["city", "district", "inds_group"])


def main() -> None:
    """전국 경쟁 매트릭스 수집 (전체 또는 특정 시/도)."""
    from src.collect.build_national_competition import collect_national_competition
    collect_national_competition()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    main()
