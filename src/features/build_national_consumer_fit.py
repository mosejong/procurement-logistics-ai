"""
전국 소비층 적합도 생성

national_district_population.csv (264개 구/시/군, 총인구+성별) +
시/도별 연령 분포 비율 (2024 주민등록인구통계 기반 추정)
→ district × age_group 추정 인구 → consumer_fit_score 산출

출력: outputs/tables/national_consumer_fit.csv
      [city, district, item_category, target_age_ratio, consumer_fit_score]

실행:
    python -m src.features.build_national_consumer_fit
"""

from pathlib import Path

import pandas as pd

from src.features.build_consumer_fit import CATEGORY_TARGET_AGE

NATIONAL_POP_PATH = Path("data/reference/national_district_population.csv")
OUT_PATH = Path("outputs/tables/national_consumer_fit.csv")

AGE_GROUPS = ["0~9세", "10대", "20대", "30대", "40대", "50대", "60대", "70대", "80대", "90세이상"]

# 시/도별 연령대 비율 (2024 행안부 주민등록인구통계 기반 추정)
# 수도권·세종: 젊은 구조 / 전남·경북·전북·강원: 고령화 구조
SIDO_AGE_RATIOS: dict[str, list[float]] = {
    #                 0~9    10대   20대   30대   40대   50대   60대   70대   80대   90+
    "서울특별시":   [0.070, 0.075, 0.145, 0.155, 0.140, 0.145, 0.120, 0.080, 0.055, 0.015],
    "부산광역시":   [0.065, 0.072, 0.120, 0.130, 0.135, 0.155, 0.145, 0.095, 0.060, 0.023],
    "대구광역시":   [0.068, 0.075, 0.120, 0.130, 0.138, 0.152, 0.138, 0.090, 0.058, 0.021],
    "인천광역시":   [0.078, 0.085, 0.135, 0.145, 0.148, 0.148, 0.120, 0.075, 0.048, 0.018],
    "광주광역시":   [0.072, 0.080, 0.135, 0.140, 0.135, 0.148, 0.130, 0.088, 0.055, 0.017],
    "대전광역시":   [0.075, 0.082, 0.135, 0.140, 0.138, 0.148, 0.125, 0.085, 0.052, 0.020],
    "울산광역시":   [0.080, 0.090, 0.120, 0.138, 0.152, 0.158, 0.120, 0.075, 0.047, 0.020],
    "세종특별자치시": [0.110, 0.100, 0.135, 0.165, 0.155, 0.140, 0.095, 0.055, 0.032, 0.013],
    "경기도":       [0.090, 0.090, 0.135, 0.155, 0.152, 0.148, 0.110, 0.068, 0.040, 0.012],
    "강원특별자치도": [0.065, 0.072, 0.110, 0.120, 0.135, 0.165, 0.155, 0.105, 0.058, 0.015],
    "충청북도":     [0.072, 0.078, 0.115, 0.125, 0.138, 0.160, 0.148, 0.095, 0.055, 0.014],
    "충청남도":     [0.072, 0.078, 0.110, 0.120, 0.138, 0.162, 0.148, 0.095, 0.058, 0.019],
    "전북특별자치도": [0.065, 0.070, 0.110, 0.118, 0.130, 0.160, 0.162, 0.110, 0.060, 0.015],
    "전라남도":     [0.060, 0.067, 0.102, 0.108, 0.122, 0.158, 0.175, 0.125, 0.065, 0.018],
    "경상북도":     [0.063, 0.070, 0.105, 0.112, 0.128, 0.160, 0.170, 0.115, 0.063, 0.014],
    "경상남도":     [0.072, 0.080, 0.112, 0.122, 0.142, 0.162, 0.150, 0.095, 0.052, 0.013],
    "제주특별자치도": [0.078, 0.085, 0.120, 0.132, 0.145, 0.158, 0.135, 0.082, 0.048, 0.017],
}

# 미매칭 시/도 fallback (전국 평균 근사)
_DEFAULT_RATIOS = [0.075, 0.080, 0.120, 0.130, 0.140, 0.155, 0.140, 0.095, 0.055, 0.010]


def build_national_age_profile(pop_df: pd.DataFrame) -> pd.DataFrame:
    """
    district × age_group 추정 인구 테이블 생성.

    [city, district, age_group, total_cnt]
    """
    records = []
    for _, row in pop_df.iterrows():
        city = row.get("city", "")
        district = row.get("district", "")
        total = row.get("total_population", 0)
        if not district or total <= 0:
            continue

        ratios = SIDO_AGE_RATIOS.get(city, _DEFAULT_RATIOS)
        for age_group, ratio in zip(AGE_GROUPS, ratios):
            records.append({
                "city": city,
                "district": district,
                "age_group": age_group,
                "total_cnt": round(total * ratio),
            })

    return pd.DataFrame(records)


def build_national_consumer_fit(pop_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    전국 district × item_category 소비층 적합도 점수 산출.

    Returns:
        DataFrame [city, district, item_category, target_age_ratio, consumer_fit_score]
    """
    if pop_df is None:
        if not NATIONAL_POP_PATH.exists():
            print(f"인구 파일 없음: {NATIONAL_POP_PATH}")
            return pd.DataFrame()
        pop_df = pd.read_csv(NATIONAL_POP_PATH, encoding="utf-8-sig")

    age_profile = build_national_age_profile(pop_df)
    if age_profile.empty:
        return pd.DataFrame()

    # district별 총 인구 (시/도별 비율을 적용했으니 단순 합산)
    district_total = (
        age_profile.groupby(["city", "district"])["total_cnt"]
        .sum()
        .rename("district_total")
        .reset_index()
    )

    records = []
    for category, target_ages in CATEGORY_TARGET_AGE.items():
        target_df = age_profile[age_profile["age_group"].isin(target_ages)]
        target_sum = (
            target_df.groupby(["city", "district"])["total_cnt"]
            .sum()
            .rename("target_cnt")
            .reset_index()
        )
        merged = target_sum.merge(district_total, on=["city", "district"])
        merged["target_age_ratio"] = (merged["target_cnt"] / merged["district_total"]).round(4)
        merged["item_category"] = category
        records.append(merged[["city", "district", "item_category", "target_age_ratio"]])

    if not records:
        return pd.DataFrame()

    result = pd.concat(records, ignore_index=True)

    # 카테고리별 min-max 정규화 → consumer_fit_score
    result["consumer_fit_score"] = (
        result.groupby("item_category")["target_age_ratio"]
        .transform(lambda x: (x - x.min()) / (x.max() - x.min() + 1e-9))
        .round(4)
    )

    return result.sort_values(["city", "district", "consumer_fit_score"], ascending=[True, True, False])


def main() -> None:
    print(f"인구 데이터 로드: {NATIONAL_POP_PATH}")
    pop_df = pd.read_csv(NATIONAL_POP_PATH, encoding="utf-8-sig")
    print(f"  {len(pop_df)}개 지역")

    result = build_national_consumer_fit(pop_df)
    if result.empty:
        print("결과 없음")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"저장: {OUT_PATH} ({len(result):,}행, {result['district'].nunique()}개 지역)")
    print(f"\n카테고리별 평균 consumer_fit_score:")
    print(result.groupby("item_category")["consumer_fit_score"].mean().sort_values(ascending=False).to_string())
    print(f"\n시/도별 커버리지:")
    print(result.groupby("city")["district"].nunique().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
