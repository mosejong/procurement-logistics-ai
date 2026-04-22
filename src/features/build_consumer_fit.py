"""
consumer_fit_score: 연령별 소비층 비중 × 품목군 주소비층 매핑

연령별 인구 데이터(행안부) + 품목군별 주요 소비층 정의
→ 자치구×품목군 단위 소비층 적합도 점수
"""

import pandas as pd
from pathlib import Path

AGE_PROFILE_PATH = Path("outputs/tables/seoul_age_profile.csv")

# 품목군별 주요 소비층 연령대 (창업자가 타겟할 B2G 수요를 발생시키는 기관 이용자 기준)
# B2C 업종은 실제 구매자 연령대 기준
CATEGORY_TARGET_AGE: dict[str, list[str]] = {
    "교육/교구":       ["0~9세", "10대", "20대"],      # 학교·어린이집 대상
    "급식/식품":       ["0~9세", "10대", "20대", "30대"],  # 학교급식·어린이집
    "의료/복지":       ["60대", "70대", "80대", "90세이상"],  # 노인복지·의료기관
    "IT/소프트웨어":   ["20대", "30대", "40대"],         # 업무 활동 인구
    "시설관리/공사":   ["30대", "40대", "50대"],         # 거주·사용 활동 인구
    "위생/방역":       ["30대", "40대", "50대", "60대"],  # 전 연령대
    "도서/콘텐츠":     ["10대", "20대", "30대"],          # 독서·문화 소비층
    "행사/홍보":       ["20대", "30대", "40대"],
    "사무용품/문구":   ["20대", "30대", "40대"],
    "가구/인테리어":   ["30대", "40대"],
    "차량/운송":       ["30대", "40대", "50대"],
    "창업/경영지원":   ["20대", "30대", "40대"],
    "환경개선/생활민원": ["40대", "50대", "60대"],
    "시설위탁/운영":   ["30대", "40대", "50대"],
    "건설/감리":       ["30대", "40대", "50대"],
    "도시정비/재개발": ["40대", "50대", "60대"],
    "회계/전문용역":   ["30대", "40대", "50대"],
    "기타":            ["20대", "30대", "40대"],
}


def build_consumer_fit_score(
    age_profile: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    자치구×품목군 소비층 적합도 점수를 계산합니다.

    Returns:
        DataFrame with [district, item_category, target_age_ratio, consumer_fit_score]
    """
    if age_profile is None:
        if not AGE_PROFILE_PATH.exists():
            return pd.DataFrame()
        age_profile = pd.read_csv(AGE_PROFILE_PATH, encoding="utf-8-sig")

    if age_profile.empty:
        return pd.DataFrame()

    # 자치구별 총 인구
    district_total = (
        age_profile.groupby("district")["total_cnt"]
        .sum()
        .rename("district_total")
        .reset_index()
    )

    records = []
    for category, target_ages in CATEGORY_TARGET_AGE.items():
        # 자치구별 타겟 연령대 인구 합산
        target_df = age_profile[age_profile["age_group"].isin(target_ages)]
        target_sum = (
            target_df.groupby("district")["total_cnt"]
            .sum()
            .rename("target_cnt")
            .reset_index()
        )
        merged = target_sum.merge(district_total, on="district")
        merged["target_age_ratio"] = (
            merged["target_cnt"] / merged["district_total"]
        ).round(4)
        merged["item_category"] = category
        records.append(merged[["district", "item_category", "target_age_ratio"]])

    if not records:
        return pd.DataFrame()

    result = pd.concat(records, ignore_index=True)

    # 0~1 min-max 정규화 → consumer_fit_score
    result["consumer_fit_score"] = result.groupby("item_category")["target_age_ratio"].transform(
        lambda x: (x - x.min()) / (x.max() - x.min() + 1e-9)
    ).round(4)

    return result.sort_values(["district", "consumer_fit_score"], ascending=[True, False])


def main() -> None:
    from src.utils.file_handler import save_csv
    result = build_consumer_fit_score()
    if result.empty:
        print("데이터 없음 — 행안부 연령 데이터를 먼저 수집하세요.")
        return
    path = save_csv(result, "outputs/tables/seoul_consumer_fit.csv")
    print(f"저장: {path}")
    print(result.head(20).to_string())


if __name__ == "__main__":
    main()
