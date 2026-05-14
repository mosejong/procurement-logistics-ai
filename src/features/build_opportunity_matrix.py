"""
자치구 × 품목군 기회 매트릭스 생성

역할:
    조달청 입찰공고 데이터를 '자치구 × 품목군(item_category_detail)' 단위로 집계하고,
    공고수·금액·최근성·경쟁도를 결합한 opportunity_score와 추천 정책 플래그를 산출합니다.

주요 상수:
    TARGET_DISTRICTS  - 수집·분석 대상 자치구 목록
    EXCLUDE_CATEGORIES - 추천에서 제외할 규제/진입장벽 카테고리
    MIN_BID_COUNT_FOR_RECOMMENDATION - 데이터부족 판단 기준 건수
    DISTRICT_PROFILES  - 대시보드·발표용 구별 특성 라벨

opportunity_score 공식:
    count_score × 0.40 + amount_score × 0.25 + recency_score × 0.15 + competition_score × 0.20
    - count_score    : 공고 수 (반복 수요 신호) — 전체 구 min-max 정규화
    - amount_score   : 총 발주 금액 (구매 규모) — 전체 구 min-max 정규화
    - recency_score  : 최근성 (1/(1+경과일/30)) — 현재 수요 여부
    - competition_score : 개방경쟁 비율 (1 - 지명경쟁 비율) — 높을수록 신규진입 용이
"""

import pandas as pd

from src.config.regions import DISTRICT_PROFILES, REGIONS, get_all_city_district_pairs
from src.preprocess.clean_bid_data import clean_bid_data
from src.preprocess.classify_agency import apply_classifications

# 전국 모든 구/시/군 — build_opportunity_matrix의 기본 대상
TARGET_DISTRICTS: list[str] = [
    district
    for districts in REGIONS.values()
    for district in districts
]

# 서울 25개 구 (하위 호환 — 기존 서울 전용 호출 코드에서 참조)
SEOUL_TARGET_DISTRICTS: list[str] = REGIONS["서울특별시"]

# 추천에서 제외할 카테고리
# 진입장벽이 높거나 허가·면허가 필요해 일반 예비창업자에게 추천하기 부적절한 업종
EXCLUDE_CATEGORIES: set[str] = {"폐기물/환경", "건설/공사", "기타/미분류"}

# 공고 건수가 이 값 미만이면 데이터부족으로 처리 — 소표본 카테고리의 과신을 방지
MIN_BID_COUNT_FOR_RECOMMENDATION = 10


def min_max_score(series: pd.Series) -> pd.Series:
    """값을 0~1 사이 점수로 바꿉니다. 공고 수/금액 규모 비교에 씁니다."""
    series = pd.to_numeric(series, errors="coerce").fillna(0)
    min_value = series.min()
    max_value = series.max()

    if max_value == min_value:
        return pd.Series(1.0, index=series.index)

    return (series - min_value) / (max_value - min_value)


def recency_score(dates: pd.Series) -> pd.Series:
    """최근 공고일수록 높은 점수를 줍니다."""
    dates = pd.to_datetime(dates, errors="coerce")

    if dates.notna().sum() == 0:
        return pd.Series(0.5, index=dates.index)

    latest_date = dates.max()
    age_days = (latest_date - dates).dt.days.fillna(365)
    return 1 / (1 + age_days / 30)


def build_opportunity_matrix(df: pd.DataFrame, target_districts: list[str] | None = None) -> pd.DataFrame:
    """
    조달 입찰공고를 '자치구 x 품목군' 단위로 집계합니다.

    item_category_detail(신 분류기) 기준으로 groupby.
    입력 df에 item_category_detail이 없으면 apply_classifications()로 자동 생성.
    출력 컬럼명은 item_category로 유지해 downstream 코드와 호환.
    """
    cleaned = clean_bid_data(df)
    districts = target_districts or TARGET_DISTRICTS
    filtered = cleaned[cleaned["district"].isin(districts)].copy()

    if filtered.empty:
        return pd.DataFrame(
            columns=[
                "district", "district_profile", "item_category", "bid_count", "amount_sum",
                "amount_mean", "latest_posted_date", "count_score", "amount_score",
                "recency_score", "opportunity_score", "recommendation_flag",
            ]
        )

    # item_category_detail이 없으면 신 분류기 적용
    if "item_category_detail" not in filtered.columns:
        filtered = apply_classifications(filtered)

    # 낙찰 소요일 = 개찰일 - 공고일 (재고회전 지표 대리변수)
    if "opengDt" in filtered.columns and "bidNtceDt" in filtered.columns:
        filtered["opengDt"] = pd.to_datetime(filtered["opengDt"], errors="coerce")
        filtered["bidNtceDt"] = pd.to_datetime(filtered["bidNtceDt"], errors="coerce")
        filtered["lead_time_days"] = (filtered["opengDt"] - filtered["bidNtceDt"]).dt.days

    has_lead = "lead_time_days" in filtered.columns

    # 경쟁도: 지명경쟁(dsgntCmptYn=Y) 여부 플래그 준비
    if "dsgntCmptYn" in filtered.columns:
        filtered["_is_open"] = (filtered["dsgntCmptYn"].str.strip().str.upper() != "Y").astype(int)
    else:
        filtered["_is_open"] = 1  # 정보 없으면 개방경쟁으로 간주

    agg_dict = {
        "bid_count": ("bid_title", "size"),
        "amount_sum": ("estimated_amount", "sum"),
        "amount_mean": ("estimated_amount", "mean"),
        "latest_posted_date": ("posted_date", "max"),
        "open_bid_ratio": ("_is_open", "mean"),  # 개방경쟁 비율 (0~1)
    }
    if has_lead:
        agg_dict["avg_lead_time_days"] = ("lead_time_days", "mean")

    # 신 분류기(item_category_detail) 기준으로 집계
    group_cols = ["district", "item_category_detail"]
    if "city" in filtered.columns:
        group_cols = ["city", "district", "item_category_detail"]

    matrix = (
        filtered.groupby(group_cols, dropna=False)
        .agg(**agg_dict)
        .reset_index()
        .rename(columns={"item_category_detail": "item_category"})
    )
    if has_lead:
        matrix["avg_lead_time_days"] = matrix["avg_lead_time_days"].round(1)
    matrix["district_profile"] = matrix["district"].map(DISTRICT_PROFILES).fillna("전국 주요 지역")
    matrix["count_score"] = min_max_score(matrix["bid_count"])
    matrix["amount_score"] = min_max_score(matrix["amount_sum"])
    matrix["recency_score"] = recency_score(matrix["latest_posted_date"])
    # competition_score: 개방경쟁 비율 그대로 사용 (0~1, 높을수록 신규진입 용이)
    matrix["competition_score"] = matrix["open_bid_ratio"].fillna(1.0).round(3)

    matrix["opportunity_score"] = (
        (
            matrix["count_score"] * 0.40
            + matrix["amount_score"] * 0.25
            + matrix["recency_score"] * 0.15
            + matrix["competition_score"] * 0.20
        )
        * 100
    ).round(2)

    # 추천 정책 플래그
    matrix["recommendation_flag"] = "추천"
    matrix.loc[matrix["item_category"].isin(EXCLUDE_CATEGORIES), "recommendation_flag"] = "제외"
    matrix.loc[
        (matrix["bid_count"] < MIN_BID_COUNT_FOR_RECOMMENDATION) &
        (matrix["recommendation_flag"] == "추천"),
        "recommendation_flag"
    ] = "데이터부족"

    base_columns = [
        "district", "district_profile", "item_category", "bid_count", "amount_sum",
        "amount_mean", "latest_posted_date", "count_score", "amount_score",
        "recency_score", "competition_score", "opportunity_score", "recommendation_flag",
    ]
    if "city" in matrix.columns:
        base_columns = ["city"] + base_columns
    if "avg_lead_time_days" in matrix.columns:
        base_columns.append("avg_lead_time_days")
    return matrix[base_columns].sort_values("opportunity_score", ascending=False).reset_index(drop=True)


def summarize_top_items_by_district(matrix: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """발표/중간점검용으로 자치구별 TOP N 품목군을 요약합니다."""
    if matrix.empty:
        return matrix.copy()

    ranked = matrix.sort_values(["district", "opportunity_score"], ascending=[True, False]).copy()
    ranked["rank"] = ranked.groupby("district").cumcount() + 1
    return ranked[ranked["rank"] <= top_n].reset_index(drop=True)
