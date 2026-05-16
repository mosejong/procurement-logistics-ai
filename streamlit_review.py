from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

import os
import signal

import pandas as pd
import streamlit as st

from src.config.regions import CITY_LABELS, REGIONS
from src.recommendation.business_type_map import search_business_type, suggest_similar


ROOT = Path(__file__).parent
TABLES_DIR = ROOT / "outputs" / "tables"
FIGURES_DIR = ROOT / "outputs" / "figures"
REPORTS_DIR = ROOT / "outputs" / "reports"
PROCESSED_DIR = ROOT / "data" / "processed"

# 전국 데이터 우선, 없으면 서울 데이터로 폴백
def _find_table(national_name: str, seoul_name: str) -> Path:
    national = TABLES_DIR / national_name
    return national if national.exists() else TABLES_DIR / seoul_name

MATRIX_PATH = _find_table("opportunity_matrix_national.csv", "seoul_opportunity_matrix.csv")
TOP_ITEMS_PATH = _find_table("top_items_by_district_national.csv", "seoul_top_items_by_district.csv")
FEATURE_PATH = TABLES_DIR / "feature_table_national.csv"
COMPETITION_PATH = _find_table("national_competition_matrix.csv", "seoul_competition_matrix.csv")
CONSUMER_FIT_PATH = _find_table("national_consumer_fit.csv", "seoul_consumer_fit.csv")
CLASSIFIED_PATH = PROCESSED_DIR / "bid_classified_national.csv"
if not CLASSIFIED_PATH.exists():
    CLASSIFIED_PATH = PROCESSED_DIR / "seoul_bid_classified.csv"
CLEANED_PATH = PROCESSED_DIR / "bid_cleaned_national.csv"
if not CLEANED_PATH.exists():
    CLEANED_PATH = PROCESSED_DIR / "seoul_bid_cleaned.csv"
HEATMAP_PATH = FIGURES_DIR / "seoul_opportunity_heatmap.png"
REPORT_PATH = REPORTS_DIR / "national_summary.md"
if not REPORT_PATH.exists():
    REPORT_PATH = REPORTS_DIR / "seoul_sample_summary.md"


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
**opportunity_score = 공고수×40% + 금액×25% + 최근성×15% + 경쟁도×20%**

| 구성 요소 | 가중치 | 원본 값 | 계산 방식 |
|---|---|---|---|
| 공고수 점수 (count_score) | 40% | bid_count | 전체 구 중 min-max 정규화 (0~1) |
| 금액 점수 (amount_score) | 25% | amount_sum | 전체 구 중 min-max 정규화 (0~1) |
| 최근성 점수 (recency_score) | 15% | latest_posted_date | 1 ÷ (1 + 경과일/30) |
| 경쟁도 점수 (competition_score) | 20% | dsgntCmptYn | 개방입찰 비율 (지명경쟁 제외) |

> **경쟁도**: 조달청 입찰공고의 `지명경쟁여부(dsgntCmptYn)` 컬럼 기반.
> 지명경쟁(기존 업체만 참여 가능)이 적을수록 신규창업자 진입 여지가 높아 점수가 높습니다.

> **공고 수가 적지만 순위가 높은 경우**: 금액이 크거나, 최근 발주이거나, 개방입찰 비율이 높기 때문입니다.
            """
        )


def build_score_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """추천 점수 구성 요소를 한눈에 보는 비교표 생성"""
    cols = ["district", "bid_count", "amount_sum", "latest_posted_date",
            "count_score", "amount_score", "recency_score", "competition_score", "opportunity_score"]
    available = [c for c in cols if c in df.columns]
    result = df[available].copy()
    if "amount_sum" in result.columns:
        result["amount_sum"] = result["amount_sum"].apply(format_won)
    for col in ["count_score", "amount_score", "recency_score", "competition_score", "opportunity_score"]:
        if col in result.columns:
            result[col] = result[col].apply(format_score)
    return result.rename(columns={
        "district": "자치구",
        "bid_count": "공고 수",
        "amount_sum": "총 금액",
        "latest_posted_date": "최근 공고일",
        "count_score": "공고수(×0.40)",
        "amount_score": "금액(×0.25)",
        "recency_score": "최근성(×0.15)",
        "competition_score": "경쟁도(×0.20)",
        "opportunity_score": "최종 점수",
    })


# ── 데이터 로드 ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="공공조달 창업기회 분석", layout="wide")

matrix_all = load_csv(MATRIX_PATH)
top_items_all = load_csv(TOP_ITEMS_PATH)
features_all = load_csv(FEATURE_PATH)
competition = load_csv(COMPETITION_PATH)
_is_national_comp = "city" in competition.columns and not competition.empty
consumer_fit = load_csv(CONSUMER_FIT_PATH)
classified_all = load_csv(CLASSIFIED_PATH)
cleaned_all = load_csv(CLEANED_PATH)

if features_all.empty:
    features_all = matrix_all.copy()

# ── 사이드바 네비게이션 ─────────────────────────────────────────────────────
page = st.sidebar.radio(
    "화면 선택",
    ["📋 프로젝트 개요", "🔍 사업 유형 검색", "🗺️ 지역 분석", "📦 품목 분석", "⚖️ 자치구 비교", "👥 소비층 적합도", "🏪 경쟁 분석", "🚚 물류 거점 분석", "📊 원천 데이터"],
)

# ── 시/도 필터 ──────────────────────────────────────────────────────────────
st.sidebar.divider()
_has_city = "city" in features_all.columns and not features_all.empty
if _has_city:
    _available_cities = sorted(features_all["city"].dropna().unique().tolist())
    _city_label_map = {c: CITY_LABELS.get(c, c) for c in _available_cities}
    _city_options = ["전체"] + [_city_label_map[c] for c in _available_cities]
    _seoul_label = _city_label_map.get("서울특별시", "서울특별시")
    _seoul_default_idx = _city_options.index(_seoul_label) if _seoul_label in _city_options else 0
    _selected_city_label = st.sidebar.selectbox(
        "시/도 선택",
        _city_options,
        index=_seoul_default_idx,
    )
    st.sidebar.caption("※ 서울이 기본으로 적용됩니다.")
    _label_city_map = {v: k for k, v in _city_label_map.items()}
    _selected_city = None if _selected_city_label == "전체" else _label_city_map.get(_selected_city_label)
else:
    _selected_city = None

def _filter_by_city(df: pd.DataFrame) -> pd.DataFrame:
    """선택된 시/도로 데이터프레임을 필터링합니다. city 컬럼이 없으면 그대로 반환."""
    if _selected_city is None or "city" not in df.columns or df.empty:
        return df
    return df[df["city"] == _selected_city].copy()

matrix = _filter_by_city(matrix_all)
features = _filter_by_city(features_all)
classified = _filter_by_city(classified_all)
cleaned = _filter_by_city(cleaned_all)
top_items = _filter_by_city(top_items_all)

st.sidebar.divider()
if st.sidebar.button("⏹ 서버 종료", type="secondary", use_container_width=True):
    st.sidebar.warning("서버를 종료합니다...")
    os.kill(os.getpid(), signal.SIGTERM)

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
                                "- 해당 품목군이 입찰 공고보다 수의계약으로 주로 처리됨"
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
                        cat_classified = classified[classified["item_category_detail"].isin(categories)]
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
                    "미용": "생활서비스", "헬스장": "관광/여가",
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
  → 자치구 / 품목군 / 금액 / 공고일 / 지명경쟁여부 정제
  → 자치구 × 품목군 매트릭스 생성
  → 공고수(40%) + 금액(25%) + 최근성(15%) + 경쟁도(20%) → opportunity_score
  → 인구/세대 보정 → bids_per_10k_population
  → TOP 품목 추천 / 히트맵 / 리포트 생성
  → 생성형 AI(Gemini)가 수치를 받아 사용자 친화적 설명 생성
        """,
        language="text",
    )

    st.header("opportunity_score 해석 기준")
    st.markdown(
        """
| 지표 | 가중치 | 의미 | 한계 |
|---|---|---|---|
| 공고 수 | 40% | 반복 수요 여부 | 기관 수 많은 구 유리 |
| 금액 규모 | 25% | 구매 규모 | 대형 1건 > 소형 다건 가능 |
| 최근성 | 15% | 현재성 | 계절성·일회성 구분 불가 |
| 경쟁도 | 20% | 신규진입 용이성 (개방입찰 비율) | 지명경쟁 외 다수경쟁 구분 불가 |

> **bids_per_10k_population** = 인구 1만 명당 공고 수. 큰 구의 규모 편향을 보정합니다.

> **avg_lead_time_days** = 입찰공고일 → 개찰일까지 평균 일수. 짧을수록 수요가 빠르게 집행됩니다 (재고회전 지표 대리변수).

> **consumer_fit_score** = 행안부 연령별 인구 데이터 기반. 품목군 주소비층 연령대 비중을 자치구 간 min-max 정규화한 값 (0~1). 높을수록 해당 자치구에 소비층이 집중되어 있음.
        """
    )

    if HEATMAP_PATH.exists():
        st.header("지역 × 품목군 히트맵")
        st.image(str(HEATMAP_PATH), use_container_width=True)

    st.header("현재 한계")
    _limit_scope = f"전국 17개 시/도 {len(cleaned):,}건 입찰공고 기준" if not cleaned.empty else "전국 17개 시/도"
    st.warning(
        f"""
- {_limit_scope} (시/도 필터로 지역 선택 가능)
- 공공수요만 반영 (민간 소비수요, 상권 데이터 미결합)
- 품목군 분류는 키워드 기반으로 일부 기타 발생 가능
- opportunity_score는 창업 성공 예측값이 아닙니다
        """
    )

# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ 지역 분석":
    st.header("지역 선택 → 추천 품목")

    if features_all.empty:
        st.warning("분석 데이터가 없습니다. `python -m src.collect.build_seoul_sample`을 실행하세요.")
    else:
        # 2중 필터: 도/시 → 시군구 (사이드바 필터와 독립)
        _tab_cities = sorted(features_all["city"].dropna().unique().tolist()) if "city" in features_all.columns else []
        _tab_city_labels = [CITY_LABELS.get(c, c) for c in _tab_cities]
        _seoul_default_label = _city_label_map.get("서울특별시", "서울특별시")
        _default_city_idx = _tab_city_labels.index(_seoul_default_label) if _seoul_default_label in _tab_city_labels else 0
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            sel_city_label = st.selectbox("시/도 선택", _tab_city_labels, index=_default_city_idx, key="region_tab_city")
        sel_city = _tab_cities[_tab_city_labels.index(sel_city_label)] if _tab_cities else None
        _city_data = features_all[features_all["city"] == sel_city] if sel_city and "city" in features_all.columns else features_all
        with col_f2:
            districts = sorted(_city_data["district"].dropna().unique().tolist())
            selected = st.selectbox("시군구 선택", districts, key="region_tab_district")

        result = _city_data[_city_data["district"] == selected].sort_values("opportunity_score", ascending=False)
        tab_classified = classified_all[classified_all["city"] == sel_city].copy() if sel_city and "city" in classified_all.columns else classified_all

        # consumer_fit_score 병합
        if not consumer_fit.empty:
            _fit_mask = consumer_fit["district"] == selected
            if "city" in consumer_fit.columns and sel_city:
                _fit_mask &= consumer_fit["city"] == sel_city
            fit_sub = consumer_fit[_fit_mask][["item_category", "consumer_fit_score"]]
            result = result.merge(fit_sub, on="item_category", how="left")

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader(f"{selected} 품목별 공공수요 점수")
            show_cols = [c for c in [
                "item_category", "bid_count", "amount_sum",
                "opportunity_score", "consumer_fit_score",
                "recommendation_flag",
                "bids_per_10k_population", "avg_lead_time_days",
            ] if c in result.columns]
            display = result[show_cols].copy()
            if "amount_sum" in display.columns:
                display["amount_sum"] = display["amount_sum"].apply(format_won)

            if "recommendation_flag" in display.columns:
                display["recommendation_flag"] = display["recommendation_flag"].map({
                    "추천": "✅ 추천",
                    "제외": "🚫 제외",
                    "데이터부족": "⚠️ 데이터부족",
                }).fillna(display["recommendation_flag"])
                st.dataframe(display, use_container_width=True, hide_index=True)
                st.caption("✅ 추천  🚫 제외: 허가·면허 필요 업종  ⚠️ 데이터부족: 공고 10건 미만")

                # 데이터부족 비율에 따라 contextual 안내
                _n_low = (result["recommendation_flag"] == "데이터부족").sum()
                _n_total = len(result)
                _pct_low = _n_low / _n_total if _n_total > 0 else 0
                if _n_low >= 3 or _pct_low >= 0.5:
                    _shortage_items = result[result["recommendation_flag"] == "데이터부족"]["item_category"].tolist()
                    if _pct_low >= 0.5:
                        st.info(
                            f"**{selected} 지역은 공고 건수가 적은 품목이 많습니다 ({_n_low}/{_n_total}개 품목 데이터부족)**\n\n"
                            "**데이터부족 = 수요가 없다는 뜻이 아닙니다.** 두 가지 가능성이 있습니다.\n\n"
                            "| 가능성 | 설명 |\n"
                            "|---|---|\n"
                            "| 🔵 블루오션 | 수요는 있지만 소액 수의계약·직접구매로 처리되어 공고가 안 뜸 |\n"
                            "| ⚪ 실제 저수요 | 해당 지역 공공기관 수요 자체가 낮음 |"
                        )
                    else:
                        st.info(
                            f"**일부 품목 {_n_low}개가 데이터부족(공고 10건 미만)입니다.** "
                            "수요 없음 vs 블루오션 — AI 판정으로 확인하세요."
                        )

                    # AI 판정 토글
                    _ai_shortage_key = f"shortage_verdict_{selected}"
                    _show_verdict = st.toggle("🤖 AI 판정 — 블루오션인지 저수요인지 분석", key=f"toggle_{_ai_shortage_key}")
                    if _show_verdict:
                        if _ai_shortage_key not in st.session_state.get("gemini_cache", {}):
                            with st.spinner("인근 지역 데이터와 비교 분석 중..."):
                                from src.recommendation.gemini_client import build_shortage_verdict, ShortageContext
                                # 같은 시/도 내 데이터부족 품목별 비교
                                _same_city = features_all[
                                    (features_all["city"] == sel_city) &
                                    (features_all["district"] != selected)
                                ] if "city" in features_all.columns else features_all
                                _total_city_dists = _same_city["district"].nunique()
                                _comparison = []
                                for _item in _shortage_items[:6]:
                                    _item_rows = _same_city[_same_city["item_category"] == _item]
                                    _with_data = (_item_rows["bid_count"] >= 10).sum()
                                    _avg = _item_rows["bid_count"].mean() if not _item_rows.empty else 0
                                    _comparison.append({
                                        "item": _item, "city": CITY_LABELS.get(sel_city, sel_city),
                                        "avg_count": float(_avg),
                                        "districts_with_data": int(_with_data),
                                        "total_districts": _total_city_dists,
                                    })
                                _dprofile = result["district_profile"].iloc[0] if "district_profile" in result.columns and not result.empty else "전국 주요 지역"
                                _sctx = ShortageContext(
                                    city=CITY_LABELS.get(sel_city, sel_city),
                                    district=selected,
                                    district_profile=_dprofile,
                                    shortage_items=_shortage_items,
                                    total_bids_in_district=int(result["bid_count"].sum()),
                                    same_city_comparison=_comparison,
                                )
                                if "gemini_cache" not in st.session_state:
                                    st.session_state["gemini_cache"] = {}
                                st.session_state["gemini_cache"][_ai_shortage_key] = build_shortage_verdict(_sctx)
                        st.markdown(st.session_state["gemini_cache"][_ai_shortage_key])
            else:
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
        rec_result = result[result.get("recommendation_flag", pd.Series("추천", index=result.index)) == "추천"] if "recommendation_flag" in result.columns else result
        top3 = rec_result.head(3)
        cols = st.columns(3)
        for i, (col, row) in enumerate(zip(cols, top3.itertuples())):
            with col:
                st.metric(
                    label=f"{i+1}위 {row.item_category}",
                    value=f"{row.opportunity_score:.1f}점",
                    delta=f"공고 {int(row.bid_count)}건",
                )

        # 과수요 판정 — 상위 추천 품목 중 공고 수가 높은 항목 경쟁 구조 분석
        _hot_rec = rec_result[rec_result["bid_count"] >= 20] if not rec_result.empty else pd.DataFrame()
        if not _hot_rec.empty:
            _overdemand_key = f"overdemand_{selected}"
            st.markdown("---")
            _hot_label = ", ".join(_hot_rec["item_category"].head(3).tolist())
            st.info(
                f"**수요 집중 품목 감지: {_hot_label}**  \n"
                "공고 건수가 많은 품목은 수요가 확실하지만 기존 납품사와의 경쟁이 치열할 수 있습니다. "
                "레드오션인지 아직 진입 여지가 있는지 AI가 판정합니다."
            )
            _show_overdemand = st.toggle("🤖 AI 판정 — 레드오션인지 진입 여지 있는지 분석", key=f"toggle_{_overdemand_key}")
            if _show_overdemand:
                if _overdemand_key not in st.session_state.get("gemini_cache", {}):
                    with st.spinner("경쟁 구조 분석 중..."):
                        from src.recommendation.gemini_client import build_overdemand_verdict, OverdemandContext
                        _same_city_all = features_all[
                            (features_all["city"] == sel_city) if "city" in features_all.columns else features_all.index.notna()
                        ]
                        _city_avg = _same_city_all.groupby("district")["bid_count"].sum().mean() if not _same_city_all.empty else 0
                        _city_max = _same_city_all["bid_count"].max() if not _same_city_all.empty else 0
                        _hot_items_data = []
                        for _hrow in _hot_rec.head(5).itertuples():
                            _hot_items_data.append({
                                "item": _hrow.item_category,
                                "bid_count": int(_hrow.bid_count),
                                "opportunity_score": float(_hrow.opportunity_score),
                                "competition_score": float(getattr(_hrow, "competition_score", 1.0)),
                                "avg_lead_time_days": getattr(_hrow, "avg_lead_time_days", "?"),
                            })
                        _dprofile = result["district_profile"].iloc[0] if "district_profile" in result.columns and not result.empty else "전국 주요 지역"
                        _octx = OverdemandContext(
                            city=CITY_LABELS.get(sel_city, sel_city),
                            district=selected,
                            district_profile=_dprofile,
                            hot_items=_hot_items_data,
                            city_avg_bid_count=float(_city_avg),
                            city_max_bid_count=float(_city_max),
                        )
                        if "gemini_cache" not in st.session_state:
                            st.session_state["gemini_cache"] = {}
                        st.session_state["gemini_cache"][_overdemand_key] = build_overdemand_verdict(_octx)
                st.markdown(st.session_state["gemini_cache"][_overdemand_key])

        # AI 공공수요 해석 (Gemini)
        st.subheader("🤖 AI 공공수요 해석")
        st.caption("조달청 입찰공고 데이터 기반 설명입니다. 창업 성공을 예측하지 않으며 공공수요 참고 지표로만 활용하세요.")

        if not top3.empty:
            from src.recommendation.gemini_client import build_demand_summary, DemandContext

            # 현재 지역의 시/도 확인
            _city_for_district = "서울특별시"
            if "city" in result.columns and not result.empty:
                _city_rows = result["city"].dropna()
                if not _city_rows.empty:
                    _city_for_district = _city_rows.iloc[0]

            # 지역 전환 감지 → 이전 지역 캐시 삭제 (잔상 방지)
            if st.session_state.get("ai_district") != selected:
                prev = st.session_state.get("ai_district", "")
                if prev:
                    st.session_state["gemini_cache"] = {
                        k: v for k, v in st.session_state.get("gemini_cache", {}).items()
                        if not k.startswith(f"{prev}__")
                    }
                st.session_state["ai_district"] = selected

            if "gemini_cache" not in st.session_state:
                st.session_state["gemini_cache"] = {}

            for i, row in enumerate(top3.itertuples()):
                flag = getattr(row, "recommendation_flag", "추천")
                cache_key = f"{selected}__{row.item_category}__{flag}"

                header_col, toggle_col = st.columns([5, 1])
                with header_col:
                    st.markdown(f"**{i+1}위 {row.item_category}** &nbsp; {row.opportunity_score:.1f}점 · {int(row.bid_count)}건")
                with toggle_col:
                    show_ai = st.toggle(
                        "AI 해석",
                        key=f"ai_toggle_{selected}_{i}",
                        value=False,
                    )

                if show_ai:
                    if cache_key not in st.session_state["gemini_cache"]:
                        with st.spinner(f"{row.item_category} 해석 생성 중..."):
                            fit_score = None
                            if not consumer_fit.empty:
                                _fm = (consumer_fit["district"] == selected) & (consumer_fit["item_category"] == row.item_category)
                                if "city" in consumer_fit.columns and sel_city:
                                    _fm &= consumer_fit["city"] == sel_city
                                fit_row = consumer_fit[_fm]
                                if not fit_row.empty:
                                    fit_score = float(fit_row.iloc[0]["consumer_fit_score"])

                            comp_score = None
                            if hasattr(row, "competition_score"):
                                try:
                                    comp_score = float(row.competition_score)
                                except (TypeError, ValueError):
                                    pass

                            ctx = DemandContext(
                                city=_city_for_district,
                                district=selected,
                                item_category=row.item_category,
                                bid_count=int(row.bid_count),
                                amount_sum=float(row.amount_sum),
                                opportunity_score=float(row.opportunity_score),
                                recommendation_flag=flag,
                                consumer_fit_score=fit_score,
                                stores_per_10k=None,
                                competition_score=comp_score,
                            )
                            st.session_state["gemini_cache"][cache_key] = build_demand_summary(ctx)

                    st.markdown(st.session_state["gemini_cache"][cache_key])

                if i < len(top3) - 1:
                    st.divider()

        # 점수 구성 요소 상세
        with st.expander("📊 품목군별 점수 구성 상세 보기"):
            st.caption("공고수·금액·최근성 각 요소 점수를 품목군 단위로 비교합니다.")
            st.dataframe(build_score_breakdown(result), use_container_width=True, hide_index=True)

        # 기관 유형 × 세부 품목 분석
        if not tab_classified.empty:
            dist_classified = tab_classified[tab_classified["district"] == selected]
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
            item_classified = classified[classified["item_category_detail"] == selected_item]
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
    st.header("두 지역 나란히 비교")
    st.caption("서로 다른 시/도 간 비교도 가능합니다. 예: 전라도 울진군 vs 경상도 구미시")

    if features_all.empty:
        st.warning("분석 데이터가 없습니다.")
    else:
        _cmp_cities = sorted(features_all["city"].dropna().unique().tolist()) if "city" in features_all.columns else []
        _cmp_labels = [CITY_LABELS.get(c, c) for c in _cmp_cities]
        _seoul_cmp_label = _city_label_map.get("서울특별시", "서울특별시")
        _seoul_cmp_idx = _cmp_labels.index(_seoul_cmp_label) if _seoul_cmp_label in _cmp_labels else 0

        col_a, col_b = st.columns(2)
        with col_a:
            city_a_label = st.selectbox("A 시/도", _cmp_labels, index=_seoul_cmp_idx, key="cmp_city_a")
            city_a = _cmp_cities[_cmp_labels.index(city_a_label)] if _cmp_cities else None
            dists_a = sorted(features_all[features_all["city"] == city_a]["district"].dropna().unique().tolist()) if city_a else []
            dist_a = st.selectbox("A 시군구", dists_a, index=0, key="cmp_dist_a")
        with col_b:
            city_b_label = st.selectbox("B 시/도", _cmp_labels, index=_seoul_cmp_idx, key="cmp_city_b")
            city_b = _cmp_cities[_cmp_labels.index(city_b_label)] if _cmp_cities else None
            dists_b = sorted(features_all[features_all["city"] == city_b]["district"].dropna().unique().tolist()) if city_b else []
            dist_b = st.selectbox("B 시군구", dists_b, index=min(1, len(dists_b) - 1) if dists_b else 0, key="cmp_dist_b")

        data_a = features_all[(features_all["city"] == city_a) & (features_all["district"] == dist_a)].set_index("item_category") if city_a else pd.DataFrame()
        data_b = features_all[(features_all["city"] == city_b) & (features_all["district"] == dist_b)].set_index("item_category") if city_b else pd.DataFrame()

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
            "`python -m src.features.build_national_consumer_fit` 를 실행하세요."
        )
    else:
        _is_national_fit = "city" in consumer_fit.columns
        tab1, tab2 = st.tabs(["자치구별 조회", "품목군별 조회"])

        with tab1:
            if _is_national_fit:
                _fit_cities = sorted(consumer_fit["city"].dropna().unique().tolist())
                _fit_city_labels = [CITY_LABELS.get(c, c) for c in _fit_cities]
                _fit_seoul_label = CITY_LABELS.get("서울특별시", "서울특별시")
                _fit_city_default = _fit_city_labels.index(_fit_seoul_label) if _fit_seoul_label in _fit_city_labels else 0
                _fit_col1, _fit_col2 = st.columns(2)
                with _fit_col1:
                    sel_fit_city_label = st.selectbox("시/도 선택", _fit_city_labels, index=_fit_city_default, key="fit_city")
                sel_fit_city = _fit_cities[_fit_city_labels.index(sel_fit_city_label)]
                _fit_for_city = consumer_fit[consumer_fit["city"] == sel_fit_city]
                with _fit_col2:
                    districts_fit = sorted(_fit_for_city["district"].dropna().unique().tolist())
                    sel_dist = st.selectbox("자치구를 선택하세요", districts_fit, key="fit_dist")
            else:
                sel_fit_city = None
                _fit_for_city = consumer_fit
                districts_fit = sorted(consumer_fit["district"].dropna().unique().tolist())
                sel_dist = st.selectbox("자치구를 선택하세요", districts_fit, key="fit_dist")

            _dist_mask = _fit_for_city["district"] == sel_dist
            dist_fit = _fit_for_city[_dist_mask].sort_values("consumer_fit_score", ascending=False)

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
- **소비층 적합도**: 분석 대상 지역 중 상대 비교 (0~1, 높을수록 해당 구에 소비층 집중)

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
                _cat_show_cols = (
                    ["city", "district", "target_age_ratio", "consumer_fit_score"]
                    if _is_national_fit
                    else ["district", "target_age_ratio", "consumer_fit_score"]
                )
                st.dataframe(
                    cat_fit[_cat_show_cols].rename(columns={
                        "city": "시/도",
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
            "`python -m src.collect.build_national_competition` 를 실행하세요."
        )
    else:
        # 국가 데이터면 시/도 필터 적용
        comp_view = competition.copy()
        if _is_national_comp and _selected_city:
            comp_view = comp_view[comp_view["city"] == _selected_city]

        if _is_national_comp:
            city_count = competition["city"].nunique()
            dist_count = competition["district"].nunique()
            st.caption(f"전국 데이터 ({city_count}개 시/도, {dist_count}개 지역) — 강원특별자치도 제외 (API 미지원)")
        else:
            st.caption("서울 데이터 (25개 자치구)")

        # 업종 선택
        inds_groups = sorted(comp_view["inds_group"].dropna().unique().tolist())
        if not inds_groups:
            st.info("선택한 시/도에 데이터가 없습니다.")
        else:
            selected_inds = st.selectbox("업종 대분류를 선택하세요", inds_groups)

            filtered = comp_view[comp_view["inds_group"] == selected_inds].sort_values(
                "stores_per_10k", ascending=False
            )

            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(f"'{selected_inds}' 업종 지역별 밀도")
                show_cols = (["city", "district"] if _is_national_comp else ["district"]) + ["store_count", "stores_per_10k"]
                show_cols = [c for c in show_cols if c in filtered.columns]
                st.dataframe(
                    filtered[show_cols].rename(columns={
                        "city": "시/도",
                        "district": "시/군/구",
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
                    top_label = f"{top.get('city','')} {top['district']}".strip() if _is_national_comp else top["district"]
                    bot_label = f"{bottom.get('city','')} {bottom['district']}".strip() if _is_national_comp else bottom["district"]
                    st.metric("경쟁 가장 치열", top_label, f"{top['stores_per_10k']} 점포/1만명")
                    st.metric("경쟁 상대적 낮음", bot_label, f"{bottom['stores_per_10k']} 점포/1만명")
                    st.markdown(
                        """
> **stores_per_10k** = 인구 1만명당 점포 수
> 수치가 낮은 지역 = 창업 시 경쟁 부담 상대적으로 적음
> 수치가 높은 지역 = 수요도 크지만 경쟁도 치열
                        """
                    )

            # 전체 업종 비교 히트맵 대용 테이블
            st.subheader("전체 업종 × 지역 점포 밀도 (인구 1만명당)")
            pivot_col = "district"
            if _is_national_comp and not _selected_city:
                st.caption("지역이 많아 특정 시/도를 선택하면 더 보기 좋습니다.")
            pivot = comp_view.pivot_table(
                index="inds_group", columns=pivot_col, values="stores_per_10k", fill_value=0
            ).round(1)
            st.dataframe(pivot, use_container_width=True)

            st.markdown("---")
            st.subheader("공공수요 vs 경쟁 포화도 비교")
            st.caption("같은 지역에서 공공수요(opportunity_score)는 높고 점포 밀도는 낮은 업종을 찾으세요.")
            if not features.empty:
                bid_cats = sorted(features["item_category"].dropna().unique().tolist())
                sel_cat = st.selectbox("비교할 품목군", bid_cats, key="comp_cat")

                feat_cols = ["city", "district", "bid_count", "opportunity_score"] if "city" in features.columns else ["district", "bid_count", "opportunity_score"]
                feat_cols = [c for c in feat_cols if c in features.columns]
                cat_bids = features[features["item_category"] == sel_cat][feat_cols].copy()
                if _selected_city and "city" in cat_bids.columns:
                    cat_bids = cat_bids[cat_bids["city"] == _selected_city]

                cat_stores_map = {
                    "급식/식자재":      "음식/카페",
                    "방역/소독":        "생활서비스",
                    "청소/환경미화":    "생활서비스",
                    "교육물품/교구":    "교육",
                    "의료/복지용품":    "의료/복지",
                    "IT장비/전산":      "기타",
                    "시설유지보수":     "기타",
                    "인쇄/홍보물":      "소매",
                    "사무용품/소모품":  "소매",
                    "차량/운송":        "기타",
                    "행사/운영용역":    "생활서비스",
                    "전문용역/컨설팅":  "기타",
                    "경비/보안":        "생활서비스",
                    "급수/전기/설비":   "기타",
                    "조경/녹지관리":    "생활서비스",
                    "보험/금융":        "기타",
                    "기타/미분류":      "기타",
                }
                mapped_inds = cat_stores_map.get(sel_cat, "기타")
                comp_cols = (["city", "district"] if _is_national_comp else ["district"]) + ["stores_per_10k"]
                comp_cols = [c for c in comp_cols if c in comp_view.columns]
                cat_comp = comp_view[comp_view["inds_group"] == mapped_inds][comp_cols].copy()

                merge_key = ["city", "district"] if (_is_national_comp and "city" in cat_bids.columns and "city" in cat_comp.columns) else ["district"]
                if not cat_comp.empty and not cat_bids.empty:
                    merged = pd.merge(cat_bids, cat_comp, on=merge_key, how="left").fillna(0)
                    merged["수요↑/경쟁↓ 점수"] = (merged["opportunity_score"] - merged["stores_per_10k"] / 10).round(2)
                    merged = merged.sort_values("수요↑/경쟁↓ 점수", ascending=False)
                    rename_map = {
                        "city": "시/도", "district": "시/군/구",
                        "bid_count": "공공수요 공고수",
                        "opportunity_score": "공공수요 점수",
                        "stores_per_10k": "경쟁 밀도(1만명당)",
                    }
                    st.dataframe(merged.rename(columns=rename_map), use_container_width=True, hide_index=True)
                    st.caption("'수요↑/경쟁↓ 점수'가 높을수록 공공수요 대비 경쟁이 낮은 유망 지역입니다.")

# ══════════════════════════════════════════════════════════════════════════════
elif page == "🚚 물류 거점 분석":
    st.header("전국 공공조달 물류 거점 분석")
    st.caption(
        "공공조달 입찰공고는 기관 위치가 고정되고 예산 집행 주기가 일정한 예측 가능한 물류 수요입니다. "
        "물리적 납품이 필요한 품목의 지역별 수요 밀도를 분석해 최적 물류 거점을 도출합니다."
    )

    # 물리적 납품 품목 (서비스 제외, 실물 운송 필요한 품목만)
    PHYSICAL_CATEGORIES = {
        "IT장비/전산", "급식/식자재", "교육물품/교구",
        "사무용품/소모품", "의료/복지용품", "인쇄/홍보물", "차량/운송",
    }

    # 권역 분류
    COVERAGE_ZONE = {
        "서울특별시": "수도권", "경기도": "수도권", "인천광역시": "수도권",
        "강원특별자치도": "강원",
        "충청북도": "중부", "충청남도": "중부", "세종특별자치시": "중부", "대전광역시": "중부",
        "전라북도": "서남부", "광주광역시": "서남부", "전라남도": "서남부",
        "대구광역시": "동남부", "경상북도": "동남부",
        "부산광역시": "동남부", "울산광역시": "동남부", "경상남도": "동남부",
        "제주특별자치도": "도서",
    }

    if features_all.empty:
        st.warning("분석 데이터가 없습니다.")
    else:
        # 시/도 × 품목 집계
        _hub_df = features_all[features_all["item_category"].isin(PHYSICAL_CATEGORIES)].copy() if "item_category" in features_all.columns else pd.DataFrame()

        if _hub_df.empty:
            st.warning("물리적 납품 품목 데이터가 없습니다.")
        else:
            _city_agg = (
                _hub_df.groupby("city")
                .agg(
                    physical_bids=("bid_count", "sum"),
                    physical_amount=("amount_sum", "sum"),
                    category_count=("item_category", "nunique"),
                )
                .reset_index()
            )

            # 허브 점수: 물리적 공고수(50%) + 금액(30%) + 품목 다양성(20%)
            from src.features.build_opportunity_matrix import min_max_score
            _city_agg["_bids_score"] = min_max_score(_city_agg["physical_bids"])
            _city_agg["_amt_score"] = min_max_score(_city_agg["physical_amount"])
            _city_agg["_cat_score"] = min_max_score(_city_agg["category_count"])
            _city_agg["hub_score"] = (
                (_city_agg["_bids_score"] * 0.50 + _city_agg["_amt_score"] * 0.30 + _city_agg["_cat_score"] * 0.20) * 100
            ).round(1)
            _city_agg["zone"] = _city_agg["city"].map(COVERAGE_ZONE).fillna("기타")
            _city_agg["city_label"] = _city_agg["city"].map(CITY_LABELS).fillna(_city_agg["city"])
            _city_agg = _city_agg.sort_values("hub_score", ascending=False).reset_index(drop=True)

            # ── 섹션 1: 허브 점수 순위 ──────────────────────────
            st.subheader("시/도별 물류 허브 점수 순위")
            st.caption("물리적 납품 품목(IT·식자재·교구·사무용품·의료용품·인쇄물·차량)의 공고 수·금액·품목 다양성 종합 점수")

            _display_agg = _city_agg[["city_label", "zone", "physical_bids", "physical_amount", "category_count", "hub_score"]].copy()
            _display_agg["physical_amount"] = _display_agg["physical_amount"].apply(format_won)
            _display_agg.insert(0, "순위", range(1, len(_display_agg) + 1))
            st.dataframe(
                _display_agg.rename(columns={
                    "city_label": "시/도", "zone": "권역", "physical_bids": "물리적 공고 수",
                    "physical_amount": "총 발주 금액", "category_count": "품목 다양성",
                    "hub_score": "허브 점수",
                }),
                use_container_width=True, hide_index=True,
            )

            # ── 섹션 2: 권역별 TOP 거점 ─────────────────────────
            st.subheader("권역별 대표 거점")
            _zone_top = (
                _city_agg.sort_values("hub_score", ascending=False)
                .groupby("zone")
                .first()
                .reset_index()[["zone", "city_label", "physical_bids", "hub_score"]]
                .sort_values("hub_score", ascending=False)
            )
            _zone_cols = st.columns(min(len(_zone_top), 4))
            for i, (col, row) in enumerate(zip(_zone_cols, _zone_top.itertuples())):
                with col:
                    tier = "🥇 1티어" if i == 0 else ("🥈 2티어" if i == 1 else ("🥉 3티어" if i == 2 else f"{i+1}위"))
                    st.metric(
                        label=f"{tier} · {row.zone}",
                        value=row.city_label,
                        delta=f"공고 {int(row.physical_bids):,}건",
                    )

            # ── 섹션 3: 품목별 수요 집중 지역 ────────────────────
            st.subheader("품목별 수요 집중 지역")
            st.caption("각 물리적 납품 품목이 가장 많이 발주되는 시/도 TOP 3")
            _cat_city = (
                _hub_df.groupby(["item_category", "city"])["bid_count"]
                .sum()
                .reset_index()
                .sort_values(["item_category", "bid_count"], ascending=[True, False])
            )
            _cat_city["city_label"] = _cat_city["city"].map(CITY_LABELS).fillna(_cat_city["city"])
            _cat_top3 = (
                _cat_city.groupby("item_category")
                .apply(lambda x: x.nlargest(3, "bid_count"))
                .reset_index(drop=True)
            )
            _pivot_rows = []
            for cat, grp in _cat_top3.groupby("item_category"):
                row_d = {"품목": cat}
                for rank, (_, r) in enumerate(grp.iterrows(), 1):
                    row_d[f"TOP{rank}"] = f"{r['city_label']} ({int(r['bid_count']):,}건)"
                _pivot_rows.append(row_d)
            if _pivot_rows:
                st.dataframe(pd.DataFrame(_pivot_rows), use_container_width=True, hide_index=True)

            # ── 섹션 4: AI 물류 허브 전략 ────────────────────────
            st.subheader("🤖 AI 물류 거점 전략 분석")
            st.caption("전국 공공수요 분포를 바탕으로 최적 1·2·3티어 물류 허브 구조를 제안합니다.")
            _show_hub_ai = st.toggle("AI 전략 분석 시작", key="hub_ai_toggle")
            if _show_hub_ai:
                _hub_ai_key = "hub_strategy_national"
                if _hub_ai_key not in st.session_state.get("gemini_cache", {}):
                    with st.spinner("전국 수요 패턴 분석 중..."):
                        from src.recommendation.gemini_client import build_hub_strategy, HubStrategyContext

                        # 후보별 주요 품목
                        _top_cats_by_city = (
                            _hub_df.groupby(["city", "item_category"])["bid_count"]
                            .sum()
                            .reset_index()
                            .sort_values(["city", "bid_count"], ascending=[True, False])
                        )
                        _candidates = []
                        for _, row in _city_agg.iterrows():
                            _top_cats = _top_cats_by_city[_top_cats_by_city["city"] == row["city"]]["item_category"].head(3).tolist()
                            _candidates.append({
                                "city": row["city_label"],
                                "zone": row["zone"],
                                "physical_bids": int(row["physical_bids"]),
                                "physical_amount": float(row["physical_amount"]),
                                "top_categories": _top_cats,
                                "hub_score": float(row["hub_score"]),
                            })

                        _hctx = HubStrategyContext(
                            hub_candidates=_candidates,
                            national_total_bids=int(_hub_df["bid_count"].sum()),
                            national_total_amount=float(_hub_df["amount_sum"].sum()),
                        )
                        if "gemini_cache" not in st.session_state:
                            st.session_state["gemini_cache"] = {}
                        st.session_state["gemini_cache"][_hub_ai_key] = build_hub_strategy(_hctx)
                st.markdown(st.session_state["gemini_cache"][_hub_ai_key])

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
