import pandas as pd

from src.preprocess.clean_bid_data import clean_bid_data
from src.preprocess.classify_agency import apply_classifications

# 1차 샘플링 대상입니다. 전국이 아니라 서울 안에서도 성격이 뚜렷한 구만 먼저 봅니다.
TARGET_DISTRICTS = ["관악구", "강남구", "마포구", "영등포구", "성동구", "종로구", "송파구"]

# 추천에서 제외할 카테고리 (진입장벽 높거나 일반 창업 불가)
EXCLUDE_CATEGORIES: set[str] = {"폐기물/환경", "건설/공사", "기타/미분류"}

# 데이터 부족 경고 카테고리 (10건 미만 기준으로 런타임에 결정)
MIN_BID_COUNT_FOR_RECOMMENDATION = 10

# 발표에서 각 구를 설명할 때 쓰는 사람이 읽는 라벨입니다.
DISTRICT_PROFILES = {
    "관악구": "청년/자취생/대학가",
    "강남구": "업무지구/고소득/IT",
    "마포구": "홍대/관광/문화콘텐츠",
    "영등포구": "오피스/금융/교통",
    "성동구": "성수/브랜드/라이프스타일",
    "종로구": "공공기관/전통상권/관광",
    "송파구": "가족주거/대형상권/복합문화",
}


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

    agg_dict = {
        "bid_count": ("bid_title", "size"),
        "amount_sum": ("estimated_amount", "sum"),
        "amount_mean": ("estimated_amount", "mean"),
        "latest_posted_date": ("posted_date", "max"),
    }
    if has_lead:
        agg_dict["avg_lead_time_days"] = ("lead_time_days", "mean")

    # 신 분류기(item_category_detail) 기준으로 집계
    matrix = (
        filtered.groupby(["district", "item_category_detail"], dropna=False)
        .agg(**agg_dict)
        .reset_index()
        .rename(columns={"item_category_detail": "item_category"})
    )
    if has_lead:
        matrix["avg_lead_time_days"] = matrix["avg_lead_time_days"].round(1)
    matrix["district_profile"] = matrix["district"].map(DISTRICT_PROFILES).fillna("서울 주요 자치구")
    matrix["count_score"] = min_max_score(matrix["bid_count"])
    matrix["amount_score"] = min_max_score(matrix["amount_sum"])
    matrix["recency_score"] = recency_score(matrix["latest_posted_date"])

    matrix["opportunity_score"] = (
        (matrix["count_score"] * 0.5 + matrix["amount_score"] * 0.3 + matrix["recency_score"] * 0.2)
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

    columns = [
        "district", "district_profile", "item_category", "bid_count", "amount_sum",
        "amount_mean", "latest_posted_date", "count_score", "amount_score",
        "recency_score", "opportunity_score", "recommendation_flag",
    ]
    if "avg_lead_time_days" in matrix.columns:
        columns.append("avg_lead_time_days")
    return matrix[columns].sort_values("opportunity_score", ascending=False).reset_index(drop=True)


def summarize_top_items_by_district(matrix: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """발표/중간점검용으로 자치구별 TOP N 품목군을 요약합니다."""
    if matrix.empty:
        return matrix.copy()

    ranked = matrix.sort_values(["district", "opportunity_score"], ascending=[True, False]).copy()
    ranked["rank"] = ranked.groupby("district").cumcount() + 1
    return ranked[ranked["rank"] <= top_n].reset_index(drop=True)
