from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).parent

# build_seoul_sample.py를 실행하면 아래 결과 파일들이 생성됩니다.
MATRIX_PATH = ROOT / "outputs" / "tables" / "seoul_opportunity_matrix.csv"
TOP_ITEMS_PATH = ROOT / "outputs" / "tables" / "seoul_top_items_by_district.csv"
CLEANED_PATH = ROOT / "data" / "processed" / "seoul_bid_cleaned.csv"
HEATMAP_PATH = ROOT / "outputs" / "figures" / "seoul_opportunity_heatmap.png"
REPORT_PATH = ROOT / "outputs" / "reports" / "seoul_sample_summary.md"


def load_csv(path: Path) -> pd.DataFrame:
    """결과 CSV가 아직 없어도 화면이 터지지 않도록 빈 DataFrame을 반환합니다."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def format_won(value: float | int | str) -> str:
    """금액을 발표 화면에서 읽기 쉽게 원 단위 문자열로 바꿉니다."""
    try:
        return f"{int(float(value)):,}원"
    except (TypeError, ValueError):
        return "-"


def make_result_insights(top_items: pd.DataFrame) -> list[str]:
    """TOP 결과표에서 발표용 한 줄 해석을 만듭니다."""
    if top_items.empty:
        return ["아직 해석할 수 있는 샘플 결과가 없습니다."]

    insights = []
    for row in top_items.sort_values("opportunity_score", ascending=False).head(4).itertuples(index=False):
        insights.append(
            f"{row.district}: {row.item_category} 관련 공고가 포착되어 "
            f"공공수요 참고 점수 {row.opportunity_score}점으로 나타났습니다."
        )
    return insights


st.set_page_config(page_title="공공조달 창업기회 샘플 점검", layout="wide")

matrix = load_csv(MATRIX_PATH)
top_items = load_csv(TOP_ITEMS_PATH)
cleaned = load_csv(CLEANED_PATH)

st.title("공공조달 데이터 기반 사업기회 탐색 중간점검")
st.caption("지금 무엇을 만들고 있는지, 어떤 결과가 나왔는지 확인하는 발표 초안형 화면")

st.header("슬라이드 1. 프로젝트 한 줄 설명")
st.info(
    "공공조달 입찰공고를 지역별·품목별 공공수요 신호로 분석해, "
    "예비창업자와 창업상담가가 참고할 수 있는 사업 아이템·입지 근거를 만드는 프로젝트입니다."
)
st.markdown("**중요한 기준:** `opportunity_score`는 창업 성공 점수가 아니라 공공수요 참고 점수입니다.")

st.header("슬라이드 2. 왜 이 프로젝트를 하는가")
st.markdown(
    """
- 물류 현장 10년 경험에서 악성재고와 재고 불균형 문제를 체감했습니다.
- 악성재고는 단순히 남은 물건이 아니라 수요를 잘못 읽은 결과라고 보았습니다.
- 창업도 지역·품목 미스매치가 생기면 재고 부담과 운영 손실로 이어질 수 있습니다.
- 공공조달 데이터를 활용해 창업 전 판단에 참고할 수 있는 수요 근거를 만들고자 했습니다.
"""
)

st.header("슬라이드 3. 현재 데이터 흐름")
st.code(
    """
조달청 입찰공고 API 수집
-> 원천 데이터 저장
-> 자치구/품목군/금액/공고일 정제
-> 지역 x 품목군 매트릭스 생성
-> 공고 수 + 금액 규모 + 최근성 점수화
-> TOP 표 + 히트맵 + 요약 리포트 생성
""",
    language="text",
)

st.header("슬라이드 4. 현재 결과물 3종 세트")
col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("1. 추천 품목 TOP3")
    st.write("자치구별로 눈에 띄는 품목군을 표로 확인합니다.")
with col2:
    st.subheader("2. 지역 x 품목 히트맵")
    st.write("어느 지역·품목 조합이 상대적으로 높은지 한눈에 봅니다.")
with col3:
    st.subheader("3. 자동 요약 리포트")
    st.write("결과와 한계를 Markdown 리포트로 저장합니다.")

if top_items.empty:
    st.warning("아직 TOP 품목 결과 파일이 없습니다. `python -m src.collect.build_seoul_sample`을 먼저 실행하세요.")
else:
    st.subheader("자치구별 추천 품목 TOP3 예시")
    show_cols = [
        "district",
        "district_profile",
        "rank",
        "item_category",
        "bid_count",
        "amount_sum",
        "opportunity_score",
    ]
    display_top = top_items[[column for column in show_cols if column in top_items.columns]].copy()
    if "amount_sum" in display_top.columns:
        display_top["amount_sum"] = display_top["amount_sum"].apply(format_won)
    st.dataframe(display_top, width="stretch")

    st.subheader("샘플 결과 한 줄 해석")
    for insight in make_result_insights(top_items):
        st.markdown(f"- {insight}")

if HEATMAP_PATH.exists():
    st.subheader("지역 x 품목군 히트맵")
    st.image(str(HEATMAP_PATH), width="stretch")

st.header("슬라이드 5. 입력-출력 구조")
if matrix.empty:
    st.warning("아직 핵심 분석표가 없습니다.")
else:
    left, right = st.columns(2)

    with left:
        st.subheader("입력 A: 지역 선택")
        selected_district = st.selectbox(
            "지역을 고르면 추천 품목을 보여줍니다.",
            sorted(matrix["district"].dropna().unique().tolist()),
        )
        district_result = matrix[matrix["district"] == selected_district].sort_values(
            "opportunity_score", ascending=False
        )
        st.dataframe(district_result, width="stretch")

    with right:
        st.subheader("입력 B: 품목군 선택")
        selected_item = st.selectbox(
            "품목군을 고르면 추천 지역을 보여줍니다.",
            sorted(matrix["item_category"].dropna().unique().tolist()),
        )
        item_result = matrix[matrix["item_category"] == selected_item].sort_values(
            "opportunity_score", ascending=False
        )
        st.dataframe(item_result, width="stretch")

    st.subheader("추천 근거")
    st.markdown(
        """
- 공고 수: 해당 지역·품목 조합이 얼마나 반복적으로 나타났는지
- 금액 규모: 해당 수요의 예산 규모가 어느 정도인지
- 최근성: 최근에도 관련 공고가 있었는지
"""
    )

st.header("실제 원천 공고 샘플")
if cleaned.empty:
    st.info("정제 데이터가 아직 없습니다.")
else:
    columns = [
        column
        for column in ["district", "bid_title", "agency_name", "item_category", "estimated_amount", "posted_date"]
        if column in cleaned.columns
    ]
    sample = cleaned[cleaned.get("district", "미상") != "미상"][columns].head(1)
    if not sample.empty:
        row = sample.iloc[0]
        st.markdown(
            f"""
**예시 공고**

- 공고명: {row.get("bid_title", "-")}
- 수요기관: {row.get("agency_name", "-")}
- 자치구: {row.get("district", "-")}
- 품목군: {row.get("item_category", "-")}
- 추정금액: {format_won(row.get("estimated_amount", 0))}
- 공고일: {row.get("posted_date", "-")}
"""
        )

    st.dataframe(cleaned[columns].head(30), width="stretch")

st.header("현재 한계와 다음 단계")
st.markdown(
    """
- 현재는 서울 일부 자치구 중심 샘플 분석입니다.
- 일부 관심 자치구는 공고 수가 부족합니다.
- 품목군 분류는 키워드 기반 초기 버전입니다.
- 인구/세대현황 및 낙찰정보는 추후 결합 예정입니다.
- `opportunity_score`는 공공수요 참고 지표이며 창업 성공 예측값이 아닙니다.
"""
)

st.header("다음 의사결정")
st.markdown(
    """
1. 관악구, 성동구, 송파구를 더 살릴지 결정
2. 품목군 이름과 키워드 사전 수정
3. 주민등록 인구 및 세대현황 API 결합
4. 낙찰정보 API 결합 여부 결정
5. 발표 대표 사례로 어떤 자치구를 보여줄지 결정
"""
)

if REPORT_PATH.exists():
    with st.expander("자동 생성 요약 리포트 보기"):
        st.markdown(REPORT_PATH.read_text(encoding="utf-8"))
