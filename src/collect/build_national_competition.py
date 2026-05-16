"""
전국 소상공인 점포 수 수집 → 경쟁 포화도 매트릭스

소상공인진흥공단 상가정보 API (divId=signguCd) 를 시/군/구 단위로 호출하여
전국 229개 지역의 업종별 점포 수를 수집합니다.

수집 제외:
    - 강원특별자치도 (API 미지원, rc=03)
    - 구 있는 시의 집계 코드 (수원시·청주시 등, 구 단위로 대체)

중간 저장:
    outputs/tables/national_competition_matrix.csv 에 점진적으로 저장합니다.
    스크립트 재실행 시 이미 수집된 (city, district) 는 건너뜁니다.

실행:
    python -m src.collect.build_national_competition
    python -m src.collect.build_national_competition --cities 부산광역시 대구광역시
"""

import argparse
import logging
import time
from pathlib import Path

import pandas as pd

from src.api.store_api import (
    API_UNSUPPORTED_CITIES,
    AGGREGATE_CITY_CODES,
    CITY_DISTRICT_SIGNGU_CD,
    _lookup_signgu_cd,
    fetch_store_counts,
)
from src.features.build_competition_matrix import INDS_GROUP_MAP, load_population_map
from src.utils.file_handler import ensure_dir

logger = logging.getLogger(__name__)

NATIONAL_POP_PATH = Path("data/reference/national_district_population.csv")
OUT_PATH = Path("outputs/tables/national_competition_matrix.csv")


def _valid_targets(cities: list[str] | None = None) -> list[tuple[str, str]]:
    """
    국가 인구 CSV 기반으로 API 호출 가능한 (city, district) 목록을 반환합니다.
    """
    if not NATIONAL_POP_PATH.exists():
        raise FileNotFoundError(f"인구 파일 없음: {NATIONAL_POP_PATH}")

    pop_df = pd.read_csv(NATIONAL_POP_PATH, encoding="utf-8-sig")
    targets = []
    for _, row in pop_df.iterrows():
        city = row["city"]
        district = row["district"]
        if cities and city not in cities:
            continue
        if city in API_UNSUPPORTED_CITIES:
            continue
        cd = _lookup_signgu_cd(city, district)
        if not cd:
            continue
        targets.append((city, district))
    return targets


def _already_collected(cities: list[str] | None = None) -> set[tuple[str, str]]:
    """기존 저장 파일에서 이미 수집된 (city, district) 셋을 반환합니다."""
    if not OUT_PATH.exists():
        return set()
    df = pd.read_csv(OUT_PATH, encoding="utf-8-sig")
    if "city" not in df.columns or "district" not in df.columns:
        return set()
    pairs = set(zip(df["city"], df["district"]))
    if cities:
        pairs = {p for p in pairs if p[0] in cities}
    return pairs


def collect_national_competition(
    cities: list[str] | None = None,
    resume: bool = True,
    delay: float = 0.3,
    max_pages: int = 10,
) -> pd.DataFrame:
    """
    전국(또는 지정 시/도) 소상공인 점포 수를 수집해 경쟁 포화도 매트릭스를 반환합니다.

    Args:
        cities:    수집할 시/도 이름 목록. None이면 전국.
        resume:    True면 기존 파일의 수집 완료 지역 재수집 스킵.
        delay:     API 호출 간 딜레이(초).
        max_pages: 지역당 최대 API 페이지 수 (1만 점포 기준). 대도시는 10,000개 샘플.

    Returns:
        DataFrame [city, district, inds_group, store_count, population, stores_per_10k]
    """
    targets = _valid_targets(cities)
    done = _already_collected(cities) if resume else set()

    remaining = [(c, d) for (c, d) in targets if (c, d) not in done]
    print(f"수집 대상: {len(targets)}개 | 완료: {len(done)}개 | 남은: {len(remaining)}개")

    if not remaining:
        print("모든 지역 수집 완료. 기존 파일을 반환합니다.")
        return pd.read_csv(OUT_PATH, encoding="utf-8-sig") if OUT_PATH.exists() else pd.DataFrame()

    pop_map = load_population_map()
    ensure_dir(str(OUT_PATH.parent))

    # 기존 결과 불러오기 (resume 모드)
    existing_frames = []
    if resume and OUT_PATH.exists():
        existing_frames.append(pd.read_csv(OUT_PATH, encoding="utf-8-sig"))

    new_frames = []
    fail_list = []

    for i, (city, district) in enumerate(remaining, 1):
        cd = _lookup_signgu_cd(city, district)
        print(f"  [{i}/{len(remaining)}] {city} {district} ({cd})", end=" ... ", flush=True)

        df = fetch_store_counts(district, city=city, max_pages=max_pages)
        if df.empty:
            fail_list.append((city, district, cd))
            print("SKIP (데이터 없음)")
            continue

        df["inds_group"] = df["inds_lv1_cd"].map(INDS_GROUP_MAP).fillna("기타")
        agg = df.groupby(["city", "district", "inds_group"])["store_count"].sum().reset_index()

        pop = pop_map.get((city, district), 0)
        agg["population"] = pop
        agg["stores_per_10k"] = agg["store_count"].apply(
            lambda s: round(s / (pop / 10_000), 2) if pop > 0 else 0.0
        )
        new_frames.append(agg)
        print(f"OK ({agg['store_count'].sum():,}개 점포)", flush=True)

        # 3개마다 중간 저장 (중단 시 데이터 보존)
        if i % 3 == 0:
            _save_checkpoint(existing_frames + new_frames)

        time.sleep(delay)

    _save_checkpoint(existing_frames + new_frames)

    if fail_list:
        print(f"\n[수집 실패 {len(fail_list)}개]")
        for city, district, cd in fail_list:
            print(f"  {city} {district} ({cd})")

    if not existing_frames and not new_frames:
        return pd.DataFrame()

    return pd.read_csv(OUT_PATH, encoding="utf-8-sig")


def _save_checkpoint(frames: list[pd.DataFrame]) -> None:
    if not frames:
        return
    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset=["city", "district", "inds_group"], keep="last")
    result = result.sort_values(["city", "district", "inds_group"])
    result.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    logger.info("중간 저장: %s (%d행)", OUT_PATH, len(result))


def main(cities: list[str] | None = None) -> None:
    scope = "전국" if not cities else " / ".join(cities)
    print(f"\n=== 전국 경쟁 분석 수집 ({scope}) ===")
    result = collect_national_competition(cities=cities)

    if result.empty:
        print("수집 결과 없음.")
        return

    print(f"\n[완료] 저장: {OUT_PATH} ({len(result):,}행)")
    print(f"  커버리지: {result['district'].nunique()}개 지역, {result['inds_group'].nunique()}개 업종")
    print(f"\n시/도별 수집 지역 수:")
    if "city" in result.columns:
        print(result.groupby("city")["district"].nunique().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description="전국 소상공인 점포 수 수집")
    parser.add_argument(
        "--cities", nargs="*",
        help="수집할 시/도 이름 (예: 부산광역시 대구광역시). 생략하면 전국 전체.",
    )
    args = parser.parse_args()
    main(cities=args.cities or None)
