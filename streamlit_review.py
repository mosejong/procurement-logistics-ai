from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st

from src.recommendation.business_type_map import search_business_type, suggest_similar


ROOT = Path(__file__).parent

MATRIX_PATH = ROOT / "outputs" / "tables" / "seoul_opportunity_matrix.csv"
TOP_ITEMS_PATH = ROOT / "outputs" / "tables" / "seoul_top_items_by_district.csv"
FEATURE_PATH = ROOT / "outputs" / "tables" / "seoul_feature_table.csv"
COMPETITION_PATH = ROOT / "outputs" / "tables" / "seoul_competition_matrix.csv"
CONSUMER_FIT_PATH = ROOT / "outputs" / "tables" / "seoul_consumer_fit.csv"
CLASSIFIED_PATH = ROOT / "data" / "processed" / "seoul_bid_classified.csv"
CLEANED_PATH = ROOT / "data" / "processed" / "seoul_bid_cleaned.csv"
HEATMAP_PATH = ROOT / "outputs" / "figures" / "seoul_opportunity_heatmap.png"
REPORT_PATH = ROOT / "outputs" / "reports" / "seoul_sample_summary.md"


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def format_won(value: float | int | str) -> str:
    try:
        return f"{int(float(value)):,}원"
    except (TypeError, ValueError):
        return "-"


def format_score(value) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def show_score_formula():
    """추천 점수 계산식 설명 expander"""
    with st.expander("📐 추천 점수(opportunity_score) 계산 방식"):
        st.markdown(
            """
**opportunity_score = 공고수 점수 × 50% + 금액 점수 × 30% + 최근성 점수 × 20%**

| 구성 요소 | 가중치 | 원본 값 | 계산 방식 |
|---|---|---|---|
| 공고수 점수 (count_score) | 50% | bid_count | 전체 구 중 min-max 정규화 (0~1) |
| 금액 점수 (amount_score) | 30% | amount_sum | 전체 구 중 min-max 정규화 (0~1) |
| 최근성 점수 (recency_score) | 20% | latest_posted_date | 1 ÷ (1 + 경과일/30) |

> **공고 수 < 이지만 추천 순위가 높은 경우**: 최근 공고일수록 최근성 점수가 높아지고,
> 금액이 클수록 금액 점수가 올라가기 때문입니다.
> 즉, 공고 2건이라도 억 단위 금액이거나 최근 발주라면 충분히 상위 순위가 될 수 있습니다.
            """
        )


def build_score_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """추천 점수 구성 요소를 한눈에 보는 비교표 생성"""
    cols = ["district", "bid_count", "amount_sum", "latest_posted_date",
            "count_score", "amount_score", "recency_score", "opportunity_score"]
    available = [c for c in cols if c in df.columns]
    result = df[available].copy()
    if "amount_sum" in result.columns:
        result["amount_sum"] = result["amount_sum"].apply(format_won)
    for col in ["count_score", "amount_score", "recency_score", "opportunity_score"]:
        if col in result.columns:
            result[col] = result[col].apply(format_score)
    return result.rename(columns={
        "district": "자치구",
        "bid_count": "공고 수",
        "amount_sum": "총 금액",
        "latest_posted_date": "최근 공고일",
        "count_score": "공고수 점수(×0.5)",
        "amount_score": "금액 점수(×0.3)",
        "recency_score": "최근성 점수(×0.2)",
        "opportunity_score": "최종 추천 점수",
    })


# ── 데이터 로드 ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="공공조달 창업기회 분석", layout="wide")

matrix = load_csv(MATRIX_PATH)
top_items = load_csv(TOP_ITEMS_PATH)
features = load_csv(FEATURE_PATH)
competition = load_csv(COMPETITION_PATH)
consumer_fit = load_csv(CONSUMER_FIT_PATH)
classified = load_csv(CLASSIFIED_PATH)
cleaned = load_csv(CLEANED_PATH)

# features가 없으면 matrix로 대체
if features.empty:
    features = matrix.copy()

# ── 사이드바 네비게이션 ─────────────────────────────────────────────────────
page = st.sidebar.radio(
    "화면 선택",
    ["📋 프로젝트 개요", "🔍 사업 유형 검색", "🗺️ 지역 분석", "📦 품목 분석", "⚖️ 자치구 비교", "👥 소비층 적합도", "🏪 경쟁 분석", "📊 원천 데이터"],
)

# ── 공통 헤더 ──────────────────────────────────────────────────────────────
st.title("공공조달 수요 기반 사업 아이템·입지 분석")
st.caption(
    "조달청 입찰공고 데이터를 지역별·품목별 공공수요 신호로 분석합니다. "
    "이 점수는 창업 성공을 예측하지 않으며, 창업상담 시 참고하는 공공수요 근거 자료입니다."
)

# ══════════════════════════════════════════════════════════════════════════════
if page == "🔍 사업 유형 검색":
    st.header("사업 유형으로 검색")
    st.caption("창업 아이템을 직접 입력하면, 공공조달 데이터에서 관련 수요 신호를 찾아드립니다.")

    query = st.text_input(
        "어떤 사업을 생각하고 계신가요?",
        placeholder="예: 문구점, 청소업체, IT회사, 교육원, 카페 ...",
    )

    if query:
        result = search_business_type(query)

        if result is None:
            st.warning(f"**'{query}'**에 해당하는 사업 유형을 찾지 못했습니다.")
            suggestions = suggest_similar(query)
            if suggestions:
                st.markdown("**비슷한 키워드로 시도해보세요:**")
                st.write(", ".join(suggestions))
        else:
            matched_key = result["matched_key"]
            biz_type = result["type"]
            note = result["note"]
            categories = result["categories"]

            # 업종 성격 배지
            type_color = {
                "B2G": "🟢",
                "B2C": "🔴",
                "B2G+B2C": "🟡",
                "B2C+B2G": "🟡",
            }.get(biz_type, "⚪")

            st.markdown(f"### {type_color} `{matched_key}` — {biz_type} 업종")
            st.info(f"**분석 기준:** {note}")

            # B2C 전용이면 결과 없음 + 안내
            if biz_type == "B2C" or not categories:
                st.error(
                    f"**'{matched_key}'는 주로 소비자 대상(B2C) 업종**입니다.\n\n"
                    "공공조달 데이터는 공공기관이 구매하는 물품·서비스 기록이라, "
                    "일반 소비자 대상 업종은 의미 있는 수요 신호가 나오지 않습니다.\n\n"
                    "**이런 업종에는 상권 데이터가 더 적합합니다:**\n"
                    "- 소상공인시장진흥공단 상권분석 (업종별 매출지수, 유동인구)\n"
                    "- 서울시 우리마을가게 상권분석 서비스\n\n"
                    "→ 현재 프로젝트의 **다음 단계(Phase 2)**에서 상권 데이터를 결합할 예정입니다."
                )

                # 관련 B2G 가능성이 있으면 추가 안내
                if categories:
                    st.markdown("---")
                    st.markdown(f"단, **공공기관 납품(B2G)** 측면도 있습니다. 관련 조달 수요를 확인해보세요:")
                    for cat in categories:
                        cat_data = features[features["item_category"] == cat] if not features.empty else pd.DataFrame()
                        if not cat_data.empty:
                            st.markdown(f"**{cat}** 조달 수요가 있는 자치구:")
                            st.dataframe(
                                cat_data[["district", "bid_count", "opportunity_score"]].sort_values(
                                    "opportunity_score", ascending=False
                                ).head(5),
                                use_container_width=True,
                                hide_index=True,
                            )
                        else:
                            st.markdown(f"**{cat}**: 현재 수집된 데이터에서 수요 없음 (직접구매 또는 소액 거래 가능성)")

            # B2G 또는 혼합이면 조달 데이터 표시
            else:
                if features.empty:
                    st.warning("분석 데이터가 없습니다. `python -m src.collect.build_seoul_sample`을 실행하세요.")
                else:
                    for cat in categories:
                        cat_data = features[features["item_category"] == cat].sort_values(
                            "opportunity_score", ascending=False
                        )

                        st.markdown(f"---\n#### 📦 `{cat}` 관련 공공수요")

                        if cat_data.empty:
                            st.warning(
                                f"**'{cat}' 조달 공고가 현재 수집 데이터에서 0건**입니다.\n\n"
                                "가능한 이유:\n"
                                "- 자치구 단위에서는 소액 수의계약으로 처리 (공개 입찰 미등록)\n"
                                "- 조달청 직접구매(MAS) 방식 활용\n"
                                "- 수집 기간(180일) 내 해당 자치구에서 공고 없음\n\n"
                                "→ 수집 기간을 늘리거나 전국 단위로 확장하면 나타날 수 있습니다."
                            )
                        else:
                            st.caption(
                                "공고 수는 수요 빈도이고, 추천 순위는 금액·최근성을 함께 반영한 종합 지표입니다. "
                                "공고 수가 적어도 금액이 크거나 최근 발주라면 순위가 더 높을 수 있습니다."
                            )
                            col1, col2 = st.columns([2, 1])
                            with col1:
                                show_cols = [c for c in [
                                    "district", "district_profile", "bid_count",
                                    "opportunity_score", "bids_per_10k_population",
                                ] if c in cat_data.columns]
                                st.dataframe(cat_data[show_cols], use_container_width=True, hide_index=True)
                            with col2:
                                top = cat_data.iloc[0]
                                st.metric("수요 1위 지역", top["district"])
                                st.metric("공고 수", f"{int(top['bid_count'])}건")
                                st.metric("opportunity_score", f"{top['opportunity_score']:.1f}")

                            # 점수 구성 요소 비교표
                            with st.expander("📊 자치구별 점수 구성 상세 보기"):
                                st.caption(
                                    "공고수(50%) + 금액(30%) + 최근성(20%) 각 요소 점수를 구 단위로 비교합니다. "
                                    "순위가 의외인 구가 있다면 이 표에서 원인을 확인하세요."
                                )
                                st.dataframe(
                                    build_score_breakdown(cat_data),
                                    use_container_width=True, hide_index=True
                                )
                            show_score_formula()

                    # 기관 유형 분석 (classified 데이터 활용)
                    if not classified.empty:
                        cat_classified = classified[classified["item_category"].isin(categories)]
                        if not cat_classified.empty:
                            st.markdown("---")
                            st.markdown("#### 🏛️ 어떤 기관이 주로 구매하나요?")
                            col_a, col_b = st.columns([1, 1])

                            with col_a:
                                agency_dist = (
                                    cat_classified.groupby("agency_type")
                                    .size()
                                    .reset_index(name="공고 수")
                                    .sort_values("공고 수", ascending=False)
                                )
                                total_bids = agency_dist["공고 수"].sum()
                                agency_dist["비율"] = (agency_dist["공고 수"] / total_bids * 100).round(1).astype(str) + "%"
                                st.dataframe(agency_dist.rename(columns={"agency_type": "기관 유형"}),
                                             use_container_width=True, hide_index=True)

                            with col_b:
                                detail_dist = (
                                    cat_classified[cat_classified["item_category_detail"] != "기타/미분류"]
                                    .groupby("item_category_detail")
                                    .size()
                                    .reset_index(name="공고 수")
                                    .sort_values("공고 수", ascending=False)
                                    .head(8)
                                )
                                if not detail_dist.empty:
                                    st.markdown("**세부 발주 유형**")
                                    st.dataframe(detail_dist.rename(columns={"item_category_detail": "세부 품목"}),
                                                 use_container_width=True, hide_index=True)

                            # 자치구 × 기관유형 교차표
                            if len(cat_classified["district"].unique()) > 1:
                                st.markdown("**자치구별 주요 발주 기관**")
                                cross = (
                                    cat_classified.groupby(["district", "agency_type"])
                                    .size()
                                    .reset_index(name="건수")
                                    .sort_values(["district", "건수"], ascending=[True, False])
                                )
                                pivot = cross.pivot_table(index="district", columns="agency_type",
                                                          values="건수", fill_value=0)
                                st.dataframe(pivot, use_container_width=True)
                                st.caption("각 자치구에서 해당 업종을 어떤 기관이 발주하는지 보여줍니다.")

                    # B2C 혼합이면 추가 안내
                    if "B2C" in biz_type:
                        st.markdown("---")
                        st.info(
                            f"**'{matched_key}'는 B2G(공공납품)와 B2C(일반소비자) 수요가 모두 있는 업종**입니다.\n\n"
                            "위 결과는 공공조달(B2G) 측면만 반영합니다. "
                            "일반 소비자 수요는 상권 데이터 결합 후 분석 가능합니다."
                        )

            # 경쟁 밀도 참고 (B2C 포함 업종)
            if not competition.empty and ("B2C" in biz_type):
                _biz_to_inds = {
                    "문구점": "소매", "카페": "음식/카페", "커피": "음식/카페",
                    "식당": "음식/카페", "음식점": "음식/카페",
                    "미용": "생활서비스", "헬스장": "스포츠",
                    "편의점": "소매", "옷가게": "소매", "약국": "의료/복지",
                    "학원": "교육", "인테리어": "생활서비스",
                }
                inds_nm = _biz_to_inds.get(matched_key)
                if inds_nm:
                    comp_data = competition[competition["inds_group"] == inds_nm].sort_values(
                        "stores_per_10k"
                    )
                    if not comp_data.empty:
                        st.markdown("---")
                        st.markdown(f"#### 🏪 '{inds_nm}' 업종 경쟁 밀도 (낮을수록 진입 여지 있음)")
                        st.dataframe(
                            comp_data[["district", "store_count", "stores_per_10k"]].rename(columns={
                                "district": "자치구",
                                "store_count": "점포 수",
                                "stores_per_10k": "인구 1만명당 점포",
                            }),
                            use_container_width=True, hide_index=True,
                        )
                        st.caption("경쟁이 낮은 지역(점포 수 적은 곳)이 상대적으로 진입 여지가 있습니다. 단, 수요도 낮을 수 있으니 유동인구 등 추가 확인 필요.")

    else:
        # 입력 전 가이드
        st.markdown("**검색 예시:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("🟢 **공공납품 가능**")
            st.markdown("청소업체, IT회사, 교육원\n도서납품, 건설, 방역")
        with col2:
            st.markdown("🟡 **공공+소비자 혼합**")
            st.markdown("학원, 식당, 인테리어\n헬스장, 약국")
        with col3:
            st.markdown("🔴 **소비자 중심**")
            st.markdown("문구점, 카페, 편의점\n미용실, 옷가게")
        st.caption("🟢는 공공조달 데이터에서 수요 신호를 찾을 수 있고, 🔴는 상권 데이터가 더 적합합니다.")

# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 프로젝트 개요":
    st.header("프로젝트 한 줄 설명")
    st.info(
        "공공조달 입찰공고를 지역별·품목별 공공수요 신호로 분석해, "
        "예비창업자와 창업상담가가 참고할 수 있는 사업 아이템·입지 근거를 만드는 프로젝트입니다."
    )

    st.header("왜 이 프로젝트인가")
    st.markdown(
        """
- 물류창고 10년 경험에서 악성재고의 공통 원인은 **수요 미스매치**였습니다.
- 창업도 같습니다. 수요가 없는 지역, 맞지 않는 품목으로 시작하면 재고 부담이 생깁니다.
- 공공조달 데이터를 통해 창업 전 단계에서 **지역별 공공수요 패턴**을 확인할 수 있습니다.
        """
    )

    st.header("현재 데이터 현황")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("수집 공고 수", f"{len(cleaned):,}건" if not cleaned.empty else "-")
    with col2:
        dist_count = features["district"].nunique() if not features.empty else 0
        st.metric("분석 자치구", f"{dist_count}개")
    with col3:
        cat_count = features["item_category"].nunique() if not features.empty else 0
        st.metric("품목군", f"{cat_count}개")
    with col4:
        st.metric("인구 보정", "적용됨" if "bids_per_10k_population" in features.columns else "미적용")

    st.header("분석 흐름")
    st.code(
        """
조달청 입찰공고 API (자치구별 수집)
  → 자치구 / 품목군 / 금액 / 공고일 정제
  → 자치구 × 품목군 매트릭스 생성
  → 공고 수(50%) + 금액(30%) + 최근성(20%) → opportunity_score
  → 인구/세대 보정 → bids_per_10k_population
  → TOP 품목 추천 / 히트맵 / 리포트 생성
        """,
        language="text",
    )

    st.header("opportunity_score 해석 기준")
    st.markdown(
        """
| 지표 | 가중치 | 의미 | 한계 |
|---|---|---|---|
| 공고 수 | 50% | 반복 수요 여부 | 기관 수 많은 구 유리 |
| 금액 규모 | 30% | 구매 규모 | 대형 1건 > 소형 다건 가능 |
| 최근성 | 20% | 현재성 | 계절성·일회성 구분 불가 |

> **bids_per_10k_population** = 인구 1만 명당 공고 수. 큰 구의 규모 편향을 보정합니다.

> **avg_lead_time_days** = 입찰공고일 → 개찰일까지 평균 일수. 짧을수록 수요가 빠르게 집행됩니다 (재고회전 지표 대리변수).

> **consumer_fit_score** = 행안부 연령별 인구 데이터 기반. 품목군 주소비층 연령대 비중을 자치구 간 min-max 정규화한 값 (0~1). 높을수록 해당 자치구에 소비층이 집중되어 있음.
        """
    )

    if HEATMAP_PATH.exists():
        st.header("지역 × 품목군 히트맵")
        st.image(str(HEATMAP_PATH), use_container_width=True)

    st.header("현재 한계")
    st.warning(
        """
- 서울 6개 자치구 샘플 분석 (관악구는 해당 API에서 공고 수 미확보)
- 공공수요만 반영 (민간 소비수요, 상권 데이터 미결합)
- 품목군 분류는 키워드 기반으로 일부 기타 발생 가능
- opportunity_score는 창업 성공 예측값이 아닙니다
        """
    )

# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ 지역 분석":
    st.header("지역 선택 → 추천 품목")

    if features.empty:
        st.warning("분석 데이터가 없습니다. `python -m src.collect.build_seoul_sample`을 실행하세요.")
    else:
        districts = sorted(features["district"].dropna().unique().tolist())
        selected = st.selectbox("자치구를 선택하세요", districts)

        result = features[features["district"] == selected].sort_values("opportunity_score", ascending=False)

        # consumer_fit_score 병합
        if not consumer_fit.empty:
            fit_sub = consumer_fit[consumer_fit["district"] == selected][
                ["item_category", "consumer_fit_score"]
            ]
            result = result.merge(fit_sub, on="item_category", how="left")

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader(f"{selected} 품목별 공공수요 점수")
            show_cols = [c for c in [
                "item_category", "bid_count", "amount_sum",
                "opportunity_score", "consumer_fit_score",
                "bids_per_10k_population", "avg_lead_time_days",
            ] if c in result.columns]
            display = result[show_cols].copy()
            if "amount_sum" in display.columns:
                display["amount_sum"] = display["amount_sum"].apply(format_won)
            st.dataframe(display, use_container_width=True, hide_index=True)

        with col2:
            st.subheader("해석 기준")
            st.markdown(
                f"""
**{selected}** 자치구의 공공조달 수요 분포입니다.

- **opportunity_score**: 공고수(50%) + 금액(30%) + 최근성(20%) 종합 점수
- **consumer_fit_score**: 해당 품목 주소비층 연령 비중 (0~1)
- **bids_per_10k_population**: 인구 1만명 당 공고 수

> 공고 수가 적어도 금액이 크거나 최근 발주라면 점수가 높을 수 있습니다.
                """
            )
            show_score_formula()

        st.subheader("TOP 3 품목군 요약")
        top3 = result.head(3)
        cols = st.columns(3)
        for i, (col, row) in enumerate(zip(cols, top3.itertuples())):
            with col:
                st.metric(
                    label=f"{i+1}위 {row.item_category}",
                    value=f"{row.opportunity_score:.1f}점",
                    delta=f"공고 {int(row.bid_count)}건",
                )

        # 점수 구성 요소 상세
        with st.expander("📊 품목군별 점수 구성 상세 보기"):
            st.caption("공고수·금액·최근성 각 요소 점수를 품목군 단위로 비교합니다.")
            st.dataframe(build_score_breakdown(result), use_container_width=True, hide_index=True)

        # 기관 유형 × 세부 품목 분석
        if not classified.empty:
            dist_classified = classified[classified["district"] == selected]
            if not dist_classified.empty:
                st.markdown("---")
                st.subheader("🏛️ 기관 유형별 수요")
                col1, col2 = st.columns(2)

                with col1:
                    agency_dist = (
                        dist_classified.groupby("agency_type")
                        .size()
                        .reset_index(name="공고 수")
                        .sort_values("공고 수", ascending=False)
                    )
                    total = agency_dist["공고 수"].sum()
                    agency_dist["비율"] = (agency_dist["공고 수"] / total * 100).round(1).astype(str) + "%"
                    st.dataframe(agency_dist.rename(columns={"agency_type": "기관 유형"}),
                                 use_container_width=True, hide_index=True)
                    st.caption(f"총 {total}건 공고 기준")

                with col2:
                    detail_dist = (
                        dist_classified[dist_classified["item_category_detail"] != "기타/미분류"]
                        .groupby("item_category_detail")
                        .size()
                        .reset_index(name="공고 수")
                        .sort_values("공고 수", ascending=False)
                        .head(10)
                    )
                    if not detail_dist.empty:
                        st.markdown("**세부 발주 유형 TOP 10**")
                        st.dataframe(detail_dist.rename(columns={"item_category_detail": "세부 유형"}),
                                     use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
elif page == "📦 품목 분석":
    st.header("품목 선택 → 적합 지역")

    if features.empty:
        st.warning("분석 데이터가 없습니다.")
    else:
        items = sorted(features["item_category"].dropna().unique().tolist())
        selected_item = st.selectbox("품목군을 선택하세요", items)

        result = features[features["item_category"] == selected_item].sort_values(
            "opportunity_score", ascending=False
        )

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader(f"'{selected_item}' 수요 지역 순위")
            show_cols = [c for c in [
                "district", "district_profile", "bid_count", "amount_sum",
                "opportunity_score", "bids_per_10k_population",
            ] if c in result.columns]
            display = result[show_cols].copy()
            if "amount_sum" in display.columns:
                display["amount_sum"] = display["amount_sum"].apply(format_won)
            st.dataframe(display, use_container_width=True, hide_index=True)

        with col2:
            st.subheader("해석")
            if not result.empty:
                top_dist = result.iloc[0]
                st.markdown(
                    f"""
**{selected_item}** 품목군의 공공수요 분포입니다.

상위 지역: **{top_dist['district']}**
- 공고 수: {int(top_dist['bid_count'])}건
- opportunity_score: {top_dist['opportunity_score']:.1f}점

> 이 품목으로 창업 또는 B2G(공공납품) 진입 시,
> 위 지역의 공공기관 수요가 상대적으로 높습니다.
                    """
                )

        # 기관 유형 분포
        if not classified.empty:
            item_classified = classified[classified["item_category"] == selected_item]
            if not item_classified.empty:
                st.markdown("---")
                st.subheader("🏛️ 주로 어떤 기관이 발주하나요?")
                col1, col2 = st.columns(2)

                with col1:
                    agency_dist = (
                        item_classified.groupby("agency_type")
                        .size()
                        .reset_index(name="공고 수")
                        .sort_values("공고 수", ascending=False)
                    )
                    total = agency_dist["공고 수"].sum()
                    agency_dist["비율"] = (agency_dist["공고 수"] / total * 100).round(1).astype(str) + "%"
                    st.dataframe(agency_dist.rename(columns={"agency_type": "기관 유형"}),
                                 use_container_width=True, hide_index=True)

                with col2:
                    detail_dist = (
                        item_classified[item_classified["item_category_detail"] != "기타/미분류"]
                        .groupby("item_category_detail")
                        .size()
                        .reset_index(name="공고 수")
                        .sort_values("공고 수", ascending=False)
                        .head(8)
                    )
                    if not detail_dist.empty:
                        st.markdown("**세부 발주 유형**")
                        st.dataframe(detail_dist.rename(columns={"item_category_detail": "세부 유형"}),
                                     use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚖️ 자치구 비교":
    st.header("두 자치구 나란히 비교")

    if features.empty:
        st.warning("분석 데이터가 없습니다.")
    else:
        districts = sorted(features["district"].dropna().unique().tolist())
        col_a, col_b = st.columns(2)
        with col_a:
            dist_a = st.selectbox("자치구 A", districts, index=0)
        with col_b:
            dist_b = st.selectbox("자치구 B", districts, index=min(1, len(districts) - 1))

        data_a = features[features["district"] == dist_a].set_index("item_category")
        data_b = features[features["district"] == dist_b].set_index("item_category")

        all_items = sorted(set(data_a.index) | set(data_b.index))

        rows = []
        for item in all_items:
            score_a = data_a.loc[item, "opportunity_score"] if item in data_a.index else 0
            score_b = data_b.loc[item, "opportunity_score"] if item in data_b.index else 0
            cnt_a = int(data_a.loc[item, "bid_count"]) if item in data_a.index else 0
            cnt_b = int(data_b.loc[item, "bid_count"]) if item in data_b.index else 0
            rows.append({
                "품목군": item,
                f"{dist_a} 점수": round(score_a, 1),
                f"{dist_a} 공고수": cnt_a,
                f"{dist_b} 점수": round(score_b, 1),
                f"{dist_b} 공고수": cnt_b,
                "우세 지역": dist_a if score_a > score_b else (dist_b if score_b > score_a else "동일"),
            })

        compare_df = pd.DataFrame(rows).sort_values(f"{dist_a} 점수", ascending=False)
        st.dataframe(compare_df, use_container_width=True, hide_index=True)

        st.caption(
            "점수 차이가 클수록 해당 품목군에서 두 지역의 공공수요 집중도 차이가 큽니다. "
            "점수 자체보다 상대적 비교 참고 자료로 활용하세요."
        )

# ══════════════════════════════════════════════════════════════════════════════
elif page == "👥 소비층 적합도":
    st.header("자치구별 품목군 소비층 적합도")
    st.caption(
        "행정안전부 연령별 인구 데이터 기반. 각 품목군의 주소비층(예: 의료/복지 → 60대 이상) 비중이 "
        "높은 자치구일수록 수요 지속성이 높을 수 있습니다."
    )

    if consumer_fit.empty:
        st.warning(
            "소비층 분석 데이터가 없습니다. "
            "`python -m src.features.build_consumer_fit` 를 실행하세요."
        )
    else:
        tab1, tab2 = st.tabs(["자치구별 조회", "품목군별 조회"])

        with tab1:
            districts_fit = sorted(consumer_fit["district"].dropna().unique().tolist())
            sel_dist = st.selectbox("자치구를 선택하세요", districts_fit, key="fit_dist")

            dist_fit = consumer_fit[consumer_fit["district"] == sel_dist].sort_values(
                "consumer_fit_score", ascending=False
            )

            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(f"{sel_dist} 품목군별 소비층 적합도")
                st.dataframe(
                    dist_fit[["item_category", "target_age_ratio", "consumer_fit_score"]].rename(columns={
                        "item_category": "품목군",
                        "target_age_ratio": "타겟 연령 비중",
                        "consumer_fit_score": "소비층 적합도 (0~1)",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            with col2:
                st.subheader("해석 기준")
                st.markdown(
                    f"""
**{sel_dist}** 자치구의 연령 인구 구성 기반 점수입니다.

- **타겟 연령 비중**: 해당 품목군의 주소비층 연령대가 전체 인구에서 차지하는 비율
- **소비층 적합도**: 7개 구 중 상대 비교 (0~1, 높을수록 해당 구에 소비층 집중)

> 예: **의료/복지**는 60대+ 비중이 높은 구에서 점수가 높음
> 예: **교육/교구**는 0~20대 비중이 높은 구에서 점수가 높음
                    """
                )

            # opportunity_score와 consumer_fit_score 결합 테이블
            if not features.empty:
                st.subheader("공공수요 점수 × 소비층 적합도 결합")
                st.caption("두 지표 모두 높은 품목군이 '공공수요도 있고 인구 구성도 맞는' 최우선 후보입니다.")
                opp_sub = features[features["district"] == sel_dist][
                    ["item_category", "bid_count", "opportunity_score"]
                ]
                combined = pd.merge(
                    dist_fit[["item_category", "consumer_fit_score"]],
                    opp_sub,
                    on="item_category",
                    how="left",
                ).fillna({"bid_count": 0, "opportunity_score": 0})
                combined["종합 점수"] = (
                    combined["opportunity_score"] * 0.6 + combined["consumer_fit_score"] * 100 * 0.4
                ).round(2)
                combined = combined.sort_values("종합 점수", ascending=False)
                st.dataframe(combined.rename(columns={
                    "item_category": "품목군",
                    "bid_count": "공고 수",
                    "opportunity_score": "공공수요 점수",
                    "consumer_fit_score": "소비층 적합도",
                }), use_container_width=True, hide_index=True)
                st.caption(
                    "종합 점수 = 공공수요 점수 × 60% + 소비층 적합도 × 100 × 40%. "
                    "가중치는 조정 가능하며, 현재는 공공수요에 더 비중을 뒀습니다."
                )

        with tab2:
            cats_fit = sorted(consumer_fit["item_category"].dropna().unique().tolist())
            sel_cat_fit = st.selectbox("품목군을 선택하세요", cats_fit, key="fit_cat")

            cat_fit = consumer_fit[consumer_fit["item_category"] == sel_cat_fit].sort_values(
                "consumer_fit_score", ascending=False
            )

            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(f"'{sel_cat_fit}' 소비층 적합 자치구 순위")
                st.dataframe(
                    cat_fit[["district", "target_age_ratio", "consumer_fit_score"]].rename(columns={
                        "district": "자치구",
                        "target_age_ratio": "타겟 연령 비중",
                        "consumer_fit_score": "소비층 적합도 (0~1)",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            with col2:
                if not cat_fit.empty:
                    top_fit = cat_fit.iloc[0]
                    st.metric("소비층 가장 많은 지역", top_fit["district"])
                    st.metric("타겟 연령 비중", f"{top_fit['target_age_ratio']:.1%}")
                    st.metric("소비층 적합도", f"{top_fit['consumer_fit_score']:.3f}")

# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏪 경쟁 분석":
    st.header("자치구별 소상공인 점포 밀도 (경쟁 포화도)")
    st.caption(
        "소상공인시장진흥공단 상권정보 기반. 인구 1만명 당 점포 수가 높을수록 해당 업종 경쟁이 치열합니다."
    )

    if competition.empty:
        st.warning(
            "경쟁 분석 데이터가 없습니다. "
            "`python -m src.features.build_competition_matrix` 를 실행하세요."
        )
    else:
        # 업종 선택
        inds_groups = sorted(competition["inds_group"].dropna().unique().tolist())
        selected_inds = st.selectbox("업종 대분류를 선택하세요", inds_groups)

        filtered = competition[competition["inds_group"] == selected_inds].sort_values(
            "stores_per_10k", ascending=False
        )

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader(f"'{selected_inds}' 업종 자치구별 밀도")
            st.dataframe(
                filtered[["district", "store_count", "stores_per_10k"]].rename(columns={
                    "district": "자치구",
                    "store_count": "점포 수",
                    "stores_per_10k": "인구 1만명당 점포",
                }),
                use_container_width=True,
                hide_index=True,
            )

        with col2:
            st.subheader("해석")
            if not filtered.empty:
                top = filtered.iloc[0]
                bottom = filtered.iloc[-1]
                st.metric("경쟁 가장 치열", top["district"], f"{top['stores_per_10k']} 점포/1만명")
                st.metric("경쟁 상대적 낮음", bottom["district"], f"{bottom['stores_per_10k']} 점포/1만명")
                st.markdown(
                    """
> **stores_per_10k** = 인구 1만명당 점포 수
> 수치가 낮은 지역 = 해당 업종 창업 시 경쟁 부담 상대적으로 적음
> 수치가 높은 지역 = 수요도 크지만 경쟁도 치열
                    """
                )

        # 전체 업종 비교 히트맵 대용 테이블
        st.subheader("전체 업종 × 자치구 점포 밀도 (인구 1만명당)")
        pivot = competition.pivot_table(
            index="inds_group", columns="district", values="stores_per_10k", fill_value=0
        ).round(1)
        st.dataframe(pivot, use_container_width=True)

        st.markdown("---")
        st.subheader("공공수요 vs 경쟁 포화도 비교")
        st.caption("같은 자치구에서 공공수요(opportunity_score)는 높고 점포 밀도는 낮은 업종을 찾으세요.")
        if not features.empty and not competition.empty:
            # 업종 선택
            bid_cats = sorted(features["item_category"].dropna().unique().tolist())
            sel_cat = st.selectbox("비교할 품목군", bid_cats, key="comp_cat")
            cat_bids = features[features["item_category"] == sel_cat][
                ["district", "bid_count", "opportunity_score"]
            ].copy()

            # inds_group 이름이 품목군과 매핑이 다르므로 직접 매핑
            cat_stores_map = {
                "급식/식품": "음식/카페",
                "위생/방역": "생활서비스",
                "교육/교구": "교육",
                "의료/복지": "의료/복지",
                "IT/소프트웨어": "기타",
                "시설관리/공사": "기타",
                "도서/콘텐츠": "소매",
                "행사/홍보": "기타",
                "사무용품/문구": "소매",
                "가구/인테리어": "소매",
                "차량/운송": "기타",
                "창업/경영지원": "기타",
                "환경개선/생활민원": "생활서비스",
                "시설위탁/운영": "생활서비스",
                "도시정비/재개발": "기타",
                "건설/감리": "기타",
                "회계/전문용역": "기타",
                "기타": "기타",
            }
            mapped_inds = cat_stores_map.get(sel_cat, "기타")
            cat_comp = competition[competition["inds_group"] == mapped_inds][
                ["district", "stores_per_10k"]
            ].copy()

            if not cat_comp.empty and not cat_bids.empty:
                merged = pd.merge(cat_bids, cat_comp, on="district", how="left").fillna(0)
                merged["수요↑/경쟁↓ 점수"] = (merged["opportunity_score"] - merged["stores_per_10k"] / 10).round(2)
                merged = merged.sort_values("수요↑/경쟁↓ 점수", ascending=False)
                st.dataframe(merged.rename(columns={
                    "district": "자치구",
                    "bid_count": "공공수요 공고수",
                    "opportunity_score": "공공수요 점수",
                    "stores_per_10k": "경쟁 밀도(1만명당)",
                }), use_container_width=True, hide_index=True)
                st.caption("'수요↑/경쟁↓ 점수'가 높을수록 공공수요 대비 경쟁이 낮은 유망 지역입니다.")

# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 원천 데이터":
    st.header("원천 공고 데이터 샘플")

    if cleaned.empty:
        st.info("정제 데이터가 없습니다. `python -m src.collect.build_seoul_sample`을 실행하세요.")
    else:
        show_cols = [c for c in [
            "district", "bid_title", "agency_name",
            "item_category", "estimated_amount", "posted_date",
        ] if c in cleaned.columns]

        dist_filter = st.multiselect(
            "자치구 필터 (비우면 전체)",
            sorted(cleaned["district"].dropna().unique().tolist()),
        )
        filtered = cleaned if not dist_filter else cleaned[cleaned["district"].isin(dist_filter)]
        display = filtered[show_cols].copy()
        if "estimated_amount" in display.columns:
            display["estimated_amount"] = display["estimated_amount"].apply(format_won)

        st.write(f"표시: {len(display)}건")
        st.dataframe(display, use_container_width=True, hide_index=True)

    if REPORT_PATH.exists():
        with st.expander("자동 생성 요약 리포트"):
            st.markdown(REPORT_PATH.read_text(encoding="utf-8"))
