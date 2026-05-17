from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

import os
import signal

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components

from src.config.regions import CITY_LABELS, REGIONS, normalize_city_name
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
MONTHLY_TREND_PATH = TABLES_DIR / "monthly_trend_national.csv"
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


KOREA_GEOJSON_PATH = ROOT / "data" / "reference" / "korea_sido.geojson"
KOREA_SIGUNGU_GEOJSON_PATH = ROOT / "data" / "reference" / "korea_sigungu.geojson"
MAP_SUMMARY_PATH = TABLES_DIR / "map_item_city_summary.csv"

# GeoJSON city 명칭 → 데이터 city 컬럼 역방향 매핑 (불일치 보정)
_GEO_TO_DATA_CITY: dict[str, str] = {
    "전라북도": "전라북도",  # opportunity_matrix 기준
}

# ── 판정 임계값 상수 (비즈니스 로직 한 곳에서 관리) ──────────────────────────
MIN_BID_DISTRICT = 5      # 시군구 드릴다운 "데이터부족" 판정 공고 건수
MIN_BID_REGION = 10       # 지역 분석탭 "데이터부족" 판정 기준
COMPETITION_WARN = 0.3    # 경쟁도 점수 "경쟁 주의" 상한
CONSUMER_FIT_GOOD = 0.6   # 소비층 적합도 "소비층 적합" 하한
HUB_SCORE_GOOD = 70       # 물류 거점 후보 점수 하한

# ── opportunity_score 내부 가중치 (build_opportunity_matrix.py와 반드시 일치) ─
W_CNT  = 0.40   # 공고수 점수 가중치
W_AMT  = 0.25   # 금액 점수 가중치
W_REC  = 0.15   # 최근성 점수 가중치
W_COMP = 0.20   # 경쟁도 점수 가중치

# ── 복합 점수 가중치 ─────────────────────────────────────────────────────────
W_OPP   = 0.6   # 기회점수 가중치 (복합 추천점수)
W_FIT   = 0.4   # 소비층 적합도 가중치 (복합 추천점수)
W_HUB_BIDS = 0.50  # 물류 거점: 공고수
W_HUB_AMT  = 0.30  # 물류 거점: 금액
W_HUB_CAT  = 0.20  # 물류 거점: 품목 다양성

# ── UI 표시 상수 ─────────────────────────────────────────────────────────────
TOP_N_HUB       = 8    # 물류 거점 Top N
TOP_N_ITEMS     = 8    # Top 품목군 N
TOP_N_MAP       = 20   # 지도 드릴다운 / 경쟁분석 상위 표시 수
RAW_PREVIEW     = 500  # 원천 데이터 미리보기 최대 행수
TREND_START_YM  = "2024-04"  # 월별 추이 표시 시작 연월

# ── 색상 상수 ────────────────────────────────────────────────────────────────
COLOR_GOOD    = "#16A34A"   # 추천 / 긍정 (초록)
COLOR_WARN    = "#F59E0B"   # 주의 / 데이터부족 (주황)
COLOR_BAD     = "#DC2626"   # 제외 / 위험 (빨강)
COLOR_PRIMARY = "#2563EB"   # 기본 강조 (파랑)
COLOR_PURPLE  = "#7C3AED"   # 소비층 적합도
COLOR_GRAY    = "#78716C"   # 기회 검토 / 중립


@st.cache_data
def load_map_summary() -> pd.DataFrame:
    """품목군×시도 선처리 집계 테이블 로드"""
    if not MAP_SUMMARY_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(MAP_SUMMARY_PATH, encoding="utf-8-sig")


@st.cache_data
def load_korea_geojson() -> dict:
    if not KOREA_GEOJSON_PATH.exists():
        return {}
    with open(KOREA_GEOJSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_sigungu_geojson() -> dict:
    if not KOREA_SIGUNGU_GEOJSON_PATH.exists():
        return {}
    with open(KOREA_SIGUNGU_GEOJSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def _build_geo_district_whitelist(geojson: dict) -> dict[str, set]:
    """GeoJSON 기반 시도 → 유효 시군구명 집합 (직접명 + 부모시 prefix 포함)"""
    import re as _re
    whitelist: dict[str, set] = {}
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        sido = props.get("sido_name", "")
        name = props.get("name", "")
        if not sido or not name:
            continue
        whitelist.setdefault(sido, set()).add(name)
        # '수원시팔달구' → '수원시' 와 같이 부모 시 이름 추출
        m = _re.match(r"(.+[시군])(.+[군구동])", name)
        if m:
            whitelist[sido].add(m.group(1))
    return whitelist


@st.cache_data
def get_sido_summary(df: pd.DataFrame) -> pd.DataFrame:
    """시/도별 opportunity_score 평균·bid_count 합계 집계"""
    if df.empty or "city" not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby("city")
        .agg(
            opportunity_score=("opportunity_score", "mean"),
            bid_count=("bid_count", "sum"),
            district_count=("district", "nunique"),
        )
        .round({"opportunity_score": 1})
        .reset_index()
    )


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    # city 컬럼이 있으면 REGIONS 정식 키로 정규화 (전북특별자치도→전라북도 등)
    if "city" in df.columns:
        df["city"] = df["city"].apply(normalize_city_name)
    return df


# ── 공통 집계 캐시 함수 ───────────────────────────────────────────────────────
@st.cache_data
def _cached_top_items(matrix: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    if matrix.empty or "item_category" not in matrix.columns:
        return pd.DataFrame()
    return (
        matrix.groupby("item_category")["bid_count"]
        .sum().sort_values(ascending=False).head(n).reset_index()
    )


@st.cache_data
def _cached_monthly_trend(cleaned: pd.DataFrame) -> pd.DataFrame:
    """개별 공고 posted_date 기준 월별 건수 집계 (matrix의 latest_posted_date 아님)"""
    if cleaned.empty or "posted_date" not in cleaned.columns:
        return pd.DataFrame()
    df = cleaned.copy()
    df["_dt"] = pd.to_datetime(df["posted_date"], errors="coerce")
    df["_ym"] = df["_dt"].dt.to_period("M").astype(str)
    return (
        df.dropna(subset=["_ym"])
        .groupby("_ym")
        .size()
        .reset_index(name="공고 수")
        .rename(columns={"_ym": "연월"})
        .sort_values("연월")
    )


@st.cache_data
def _cached_hub_city(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return pd.DataFrame()
    cols = {c: (c, "sum" if c in ("bid_count", "amount_sum") else "mean")
            for c in ["bid_count", "amount_sum", "opportunity_score", "competition_score"]
            if c in matrix.columns}
    if "district" in matrix.columns:
        cols["district_count"] = ("district", "nunique")
    return matrix.groupby(["city", "item_category"]).agg(**cols).round(2).reset_index()


@st.cache_data
def _cached_region_summary(matrix: pd.DataFrame, city: str | None) -> pd.DataFrame:
    if matrix.empty:
        return pd.DataFrame()
    df = matrix[matrix["city"] == city] if city else matrix
    if df.empty:
        return pd.DataFrame()
    cols = {c: (c, "mean" if c not in ("bid_count", "amount_sum") else "sum")
            for c in ["opportunity_score", "competition_score", "bid_count"]
            if c in df.columns}
    return df.groupby("district").agg(**cols).round(2).reset_index() if "district" in df.columns else pd.DataFrame()


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
    with st.expander("📐 분석 점수 해석 기준"):
        st.markdown(
            f"""
### 1. 기회점수 (opportunity_score) — 0~100점
공공조달 수요의 크기·빈도·최근성·진입장벽을 종합한 창업 기회 점수입니다.

**opportunity_score = 공고수×{int(W_CNT*100)}% + 금액×{int(W_AMT*100)}% + 최근성×{int(W_REC*100)}% + 경쟁도×{int(W_COMP*100)}%**

| 구성 요소 | 가중치 | 원본 값 | 계산 방식 |
|---|---|---|---|
| 공고수 점수 (count_score) | {int(W_CNT*100)}% | bid_count | 전체 지역 min-max 정규화 (0~1) |
| 금액 점수 (amount_score) | {int(W_AMT*100)}% | amount_sum | 전체 지역 min-max 정규화 (0~1) |
| 최근성 점수 (recency_score) | {int(W_REC*100)}% | posted_date | 1 ÷ (1 + 경과일/30) |
| 경쟁도 점수 (competition_score) | {int(W_COMP*100)}% | dsgntCmptYn | 개방입찰 비율 (지명경쟁 낮을수록 높음) |

> 공고 수가 적어도 금액이 크거나 최근 발주이거나 개방입찰 비율이 높으면 점수가 높을 수 있습니다.

---

### 2. 소비층 적합도 (consumer_fit_score) — 0~1점
해당 품목의 주요 소비 연령대와 지역 인구 구성의 일치도입니다.

- **높을수록**: 그 품목을 많이 소비하는 연령대가 해당 지역에 많이 거주
- 예: 의료·복지용품 → 고령 인구 비중이 높은 지역에서 적합도 높음
- 지역별 10세 단위 인구 비율 × 품목군 연령 가중치 내적(dot product)으로 계산

---

### 3. 경쟁 포화도 (stores_per_10k) — 인구 1만명당 유사업체 수
공공조달 납품을 경쟁하는 지역 내 유사 업체 수를 인구 대비로 측정합니다.

- **낮을수록 블루오션**: 수요 대비 공급자가 적어 신규 진입 여지가 큼
- **높을수록 레드오션**: 이미 유사 업체가 포화 상태, 가격 경쟁 심화
- 출처: 국세청 사업체 통계 기반 업종 코드별 업체 수

---

### 4. 물류 거점 점수 (hub_score) — 0~100점
납품 물류의 편의성·접근성을 나타냅니다.

- 공공기관 밀도, 수도권 접근성, 고속도로 IC 근접도 등 인프라 가중 합산
- **높을수록**: 다양한 기관에 납품하기 유리한 물류 거점 위치
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
        "count_score": f"공고수(×{W_CNT})",
        "amount_score": f"금액(×{W_AMT})",
        "recency_score": f"최근성(×{W_REC})",
        "competition_score": f"경쟁도(×{W_COMP})",
        "opportunity_score": "최종 점수",
    })


# ── 데이터 로드 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="공공조달 창업기회 분석",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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

# 사이드바 미사용 — 시/도 필터는 각 상세 탭에서 처리
_selected_city = None

def _filter_by_city(df: pd.DataFrame) -> pd.DataFrame:
    if _selected_city is None or "city" not in df.columns or df.empty:
        return df
    return df[df["city"] == _selected_city].copy()

# ── 전역 session_state 초기화 ────────────────────────────────────────────────
if "ctx_city" not in st.session_state:
    st.session_state["ctx_city"] = None  # None = 전국
if "ctx_cat" not in st.session_state:
    st.session_state["ctx_cat"] = "전체"
if "_nav_tab_idx" not in st.session_state:
    st.session_state["_nav_tab_idx"] = None

matrix = matrix_all
features = features_all
classified = classified_all
cleaned = cleaned_all
top_items = top_items_all

# GeoJSON 기반 시도-시군구 whitelist (잘못 분류된 지역 필터 목적)
_sigungu_geo_global = load_sigungu_geojson()
_geo_district_whitelist = _build_geo_district_whitelist(_sigungu_geo_global) if _sigungu_geo_global else {}


# ── 서비스 헤더 (모든 탭 공통) ──────────────────────────────────────────────
st.markdown(
    '<div style="padding:6px 0 14px 0;">'
    '<h1 style="font-size:2rem;font-weight:800;color:#1E293B;margin-bottom:4px;line-height:1.2;">'
    '공공조달 수요 기반 입지 · 물류 거점 분석</h1>'
    '<p style="font-size:0.88rem;color:#64748B;margin:0;">'
    '나라장터 전국 입찰 데이터 기반 · 창업 입지 탐색 인터페이스</p>'
    '</div>',
    unsafe_allow_html=True,
)

# ── 상단 탭 네비게이션 ──────────────────────────────────────────────────────
_TAB_LABELS = [
    "🌏 전국 지도", "🔍 사업 유형 검색", "🗺️ 지역 분석",
    "📦 품목 분석", "⚖️ 자치구 비교", "👥 소비층 적합도",
    "🏪 경쟁 분석", "🚚 물류 거점 분석", "🔬 분석 근거 데이터", "📋 프로젝트 개요",
]
(
    tab_map, tab_search, tab_region,
    tab_item, tab_compare, tab_consumer,
    tab_competition, tab_logistics, tab_raw, tab_overview,
) = st.tabs(_TAB_LABELS)

# ── JS 탭 전환 (버튼 클릭 후 다음 rerun에서 실행) ─────────────────────────────
_pending_nav = st.session_state.get("_nav_tab_idx")
if _pending_nav is not None:
    del st.session_state["_nav_tab_idx"]
    components.html(
        f"""<script>
        setTimeout(function(){{
            var t = window.parent.document.querySelectorAll('.stTabs [role="tab"]');
            if (t && t.length > {_pending_nav}) t[{_pending_nav}].click();
        }}, 200);
        </script>""",
        height=0,
    )

# ══════════════════════════════════════════════════════════════════════════════
with tab_map:
    map_summary = load_map_summary()
    geojson = load_korea_geojson()
    sigungu_geojson = load_sigungu_geojson()

    # ── 상수 / 옵션 ───────────────────────────────────────────────────────────
    _item_cats = (
        sorted(map_summary["item_category"].dropna().unique().tolist())
        if not map_summary.empty else []
    )
    _city_list = (
        sorted(map_summary["city"].dropna().unique().tolist())
        if not map_summary.empty else []
    )
    _METRIC_OPTIONS = {
        "기회점수":       "opportunity_score",
        "보정 점수":      "adjusted_score",
        "공고수":         "bid_count",
        "경쟁도":         "competition_score",
        "소비층 적합도":  "consumer_fit_score",
        "물류 거점 점수": "hub_score",
    }
    _LABEL_COLOR = {
        "고기회 지역":    COLOR_GOOD,
        "소비층 적합":    COLOR_PRIMARY,
        "물류 거점 후보": COLOR_PURPLE,
        "경쟁 주의":      COLOR_BAD,
        "데이터 부족":    "#6B7280",
        "기회 검토":      COLOR_GRAY,
    }

    # ── session_state 초기화 ──────────────────────────────────────────────────
    for _k, _v in [
        ("map_city_val", "전국"),
        ("map_drilldown_city", None),
        ("map_cat", "전체"),
        ("map_metric", "기회점수"),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # ── 3열: 필터(2) | 지도(6) | 패널(3) ────────────────────────────────────
    col_filter, col_map_area, col_panel = st.columns([2, 6, 3])

    with col_filter:
        st.markdown("**주제 선택**")
        selected_metric_label = st.selectbox(
            "지도 기준", list(_METRIC_OPTIONS.keys()),
            key="map_metric",
            label_visibility="collapsed",
        )
        st.markdown("**품목군 선택**")
        selected_cat = st.selectbox(
            "품목군 선택",
            ["전체"] + _item_cats,
            key="map_cat",
            label_visibility="collapsed",
        )
        st.markdown("**지역 선택**")
        _region_opts = ["전국"] + _city_list
        _region_idx = (
            _region_opts.index(st.session_state["map_city_val"])
            if st.session_state["map_city_val"] in _region_opts else 0
        )
        selected_region = st.selectbox(
            "지역 선택",
            _region_opts,
            index=_region_idx,
            label_visibility="collapsed",
            help="지역 선택 시 시군구 지도가 바로 표시됩니다. '전국' 선택 시 전체 시도 지도로 돌아갑니다.",
        )
        st.session_state["map_city_val"] = selected_region

        # ── 점수 산정 근거 ─────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown(
            '<p style="font-size:11px;font-weight:700;color:#475569;margin:0 0 6px 0;">📐 점수 산정 근거</p>',
            unsafe_allow_html=True,
        )
        _score_desc = {
            "기회점수":       "공고수(40%) + 금액(25%) + 최근성(15%) + 경쟁도(20%) 가중 합산. 전체 지역 min-max 정규화.",
            "보정 점수":      "기회점수 × 5년 생존율 × (1 - 소멸률). KOSIS 신생기업 통계 반영.",
            "공고수":         "나라장터 입찰공고 건수 합계. 공공수요 빈도를 직접 반영.",
            "경쟁도":         "지명경쟁 제외 비율. 높을수록 신규 업체 진입 가능한 개방입찰 多.",
            "소비층 적합도":  "품목 주소비층 연령대 비중. 행안부 연령별 인구 기반 (0~1).",
            "물류 거점 점수": "품목군 내 공고수 min-max 정규화 (0~100). 납품 물리적 수요 집중도.",
        }
        for _k, _v in _score_desc.items():
            st.markdown(
                f'<p style="font-size:10px;color:#64748B;margin:0 0 4px 0;">'
                f'<b style="color:#334155;">{_k}</b><br>{_v}</p>',
                unsafe_allow_html=True,
            )

    _color_col = _METRIC_OPTIONS[selected_metric_label]
    _selected_city: str | None = None if selected_region == "전국" else selected_region
    _drilldown_city: str | None = st.session_state.get("map_drilldown_city")

    # 드롭다운 선택 → 즉시 드릴다운 (시군구 지도 표시)
    if _selected_city and _drilldown_city != _selected_city:
        st.session_state["map_drilldown_city"] = _selected_city
        st.rerun()
    elif not _selected_city and _drilldown_city is not None:
        st.session_state["map_drilldown_city"] = None
        st.rerun()

    # 최신 drilldown 도시로 동기화
    _drilldown_city = st.session_state.get("map_drilldown_city")

    # ctx_city 전역 동기화 (drilldown 우선, 없으면 dropdown)
    st.session_state["ctx_city"] = _drilldown_city or _selected_city

    # ── 전국 시도별 집계 ──────────────────────────────────────────────────────
    if not map_summary.empty:
        if selected_cat == "전체":
            _map_df = (
                map_summary.groupby("city")
                .agg(
                    opportunity_score=("opportunity_score", "mean"),
                    bid_count=("bid_count", "sum"),
                    competition_score=("competition_score", "mean"),
                    consumer_fit_score=("consumer_fit_score", "mean"),
                    hub_score=("hub_score", "mean"),
                    district_count=("district_count", "sum"),
                )
                .round(2).reset_index()
            )
            # 전체 집계 시 0~100 정규화 컬럼 보정
            for _raw, _col100 in [
                ("opportunity_score", "opp_score_100"),
                ("consumer_fit_score", "consumer_fit_100"),
                ("competition_score", "competition_100"),
            ]:
                if _raw in _map_df.columns:
                    _mn, _mx = _map_df[_raw].min(), _map_df[_raw].max()
                    if _mx > _mn:
                        _map_df[_col100] = ((_map_df[_raw] - _mn) / (_mx - _mn) * 100).round(1)
                    else:
                        _map_df[_col100] = 50.0
        else:
            _map_df = map_summary[map_summary["item_category"] == selected_cat].copy()
    else:
        _map_df = pd.DataFrame()

    if not _map_df.empty and _color_col not in _map_df.columns:
        _color_col = "opportunity_score"

    def _make_panel_gauges(metrics: list) -> go.Figure:
        """(label, value_0_100, color, invert) 리스트 → 2×N Plotly 반원 게이지 Figure"""
        n = len(metrics)
        cols = 2
        rows = (n + 1) // 2
        specs = [[{"type": "indicator"} for _ in range(cols)] for _ in range(rows)]
        fig = make_subplots(
            rows=rows, cols=cols,
            specs=specs,
            vertical_spacing=0.18,
            horizontal_spacing=0.08,
        )
        for idx, (label, val, color, invert) in enumerate(metrics):
            r, c = divmod(idx, cols)
            v = min(max(float(val or 0), 0), 100)
            bar_color = (
                ("#16A34A" if v < 40 else ("#F59E0B" if v < 70 else "#DC2626"))
                if invert else color
            )
            fig.add_trace(go.Indicator(
                mode="gauge+number",
                value=v,
                title={"text": label, "font": {"size": 10, "color": "#64748B"}},
                gauge={
                    "axis": {"range": [0, 100], "showticklabels": False, "ticks": ""},
                    "bar": {"color": bar_color, "thickness": 0.55},
                    "bgcolor": "#F1F5F9",
                    "borderwidth": 0,
                    "steps": [{"range": [0, 100], "color": "#F1F5F9"}],
                    "shape": "angular",
                },
                number={"font": {"size": 15, "color": "#1E293B"}},
            ), row=r + 1, col=c + 1)
        fig.update_layout(
            height=130 * rows,
            margin={"t": 20, "b": 0, "l": 5, "r": 5},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    # ── 드릴다운 시도의 시군구 집계 ──────────────────────────────────────────
    if _drilldown_city is not None and not matrix_all.empty:
        _src_d = matrix_all[matrix_all["city"] == _drilldown_city].copy()
        if selected_cat != "전체":
            _src_d = _src_d[_src_d["item_category"] == selected_cat]

        _agg_d: dict = {
            "bid_count":         ("bid_count",         "sum"),
            "opportunity_score": ("opportunity_score",  "mean"),
        }
        if "competition_score" in _src_d.columns:
            _agg_d["competition_score"] = ("competition_score", "mean")
        if "amount_sum" in _src_d.columns:
            _agg_d["amount_sum"] = ("amount_sum", "sum")

        _dist_df = _src_d.groupby("district").agg(**_agg_d).round(2).reset_index()

        # 오분류 district 제거: 해당 시도 소속 시군구 + 시도명 자체만 허용
        _valid_d = set(REGIONS.get(_drilldown_city, []))
        if _valid_d:
            # 타 시도 district 제거, 시도명 자체(=district없는 집계행)도 제외
            _dist_df = _dist_df[_dist_df["district"].isin(_valid_d)]

        # 소비층 적합도 조인
        if not consumer_fit.empty and "consumer_fit_score" in consumer_fit.columns and "city" in consumer_fit.columns:
            _cf_d = consumer_fit[consumer_fit["city"] == _drilldown_city]
            if selected_cat != "전체" and "item_category" in _cf_d.columns:
                _cf_d = _cf_d[_cf_d["item_category"] == selected_cat]
            if not _cf_d.empty:
                _cf_grp = _cf_d.groupby("district")["consumer_fit_score"].mean().reset_index()
                _dist_df = _dist_df.merge(_cf_grp, on="district", how="left")

        # hub_score: 시도 내 bid_count 정규화 0~100
        _bmax = _dist_df["bid_count"].max() if not _dist_df.empty else 1
        _dist_df["hub_score"] = (_dist_df["bid_count"] / max(_bmax, 1) * 100).round(1)

        # 판정 라벨
        _opp_q75_d = _dist_df["opportunity_score"].quantile(0.75) if not _dist_df.empty else 0

        def _djlabel(r: pd.Series) -> str:
            if r["bid_count"] < MIN_BID_DISTRICT:
                return "데이터 부족"
            if r["opportunity_score"] >= _opp_q75_d:
                return "고기회 지역"
            if r.get("competition_score", 1.0) < COMPETITION_WARN:
                return "경쟁 주의"
            if r.get("consumer_fit_score", 0.0) > CONSUMER_FIT_GOOD:
                return "소비층 적합"
            if r.get("hub_score", 0.0) >= HUB_SCORE_GOOD:
                return "물류 거점 후보"
            return "기회 검토"

        _dist_df["judgment_label"] = _dist_df.apply(_djlabel, axis=1)
        _dist_sort = _color_col if _color_col in _dist_df.columns else "opportunity_score"
        _dist_df = _dist_df.sort_values(_dist_sort, ascending=False).reset_index(drop=True)
    else:
        _dist_df = pd.DataFrame()

    # ── 지도 영역 ─────────────────────────────────────────────────────────────
    with col_map_area:
        if _drilldown_city is None:
            # ── 전국 choropleth ────────────────────────────────────────────
            if geojson and not _map_df.empty and _color_col in _map_df.columns:
                _hover = {
                    c: True for c in
                    ["opportunity_score", "bid_count", "competition_score",
                     "consumer_fit_score", "district_count"]
                    if c in _map_df.columns
                }
                fig = px.choropleth(
                    _map_df, geojson=geojson,
                    locations="city", featureidkey="properties.name",
                    color=_color_col, hover_data=_hover,
                    color_continuous_scale="Blues",
                    labels={
                        "city": "시/도", "opportunity_score": "기회점수",
                        "bid_count": "공고수", "competition_score": "경쟁도",
                        "consumer_fit_score": "소비층 적합도",
                        "hub_score": "물류점수", "district_count": "지역수",
                    },
                )
                fig.update_geos(
                    visible=False, showframe=False,
                    lataxis={"range": [32.8, 38.9]},
                    lonaxis={"range": [124.8, 130.0]},
                )
                fig.update_layout(
                    margin={"r": 0, "t": 0, "l": 0, "b": 0},
                    height=600,
                    coloraxis_colorbar=dict(title=selected_metric_label, thickness=12, len=0.7),
                    paper_bgcolor="rgba(0,0,0,0)",
                    geo=dict(bgcolor="rgba(0,0,0,0)"),
                )
                _map_event = st.plotly_chart(
                    fig, use_container_width=True,
                    on_select="rerun", key="national_map",
                )
                # 시도 클릭 → 드릴다운
                if (
                    _map_event
                    and hasattr(_map_event, "selection")
                    and _map_event.selection.points
                ):
                    _clicked = _map_event.selection.points[0].get("location")
                    if _clicked and _clicked in _city_list:
                        st.session_state["map_city_val"] = _clicked
                        st.rerun()
                st.caption("시도를 클릭하거나 좌측 드롭다운에서 선택하면 시군구 지도로 이동합니다")
            else:
                st.info("선택한 품목군의 전국 데이터가 없습니다.")

        else:
            # ── 시도 drill-down: 시군구 choropleth ────────────────────────
            _back_col, _title_col = st.columns([2, 8])
            with _back_col:
                if st.button("← 전국"):
                    st.session_state["map_drilldown_city"] = None
                    st.session_state["map_city_val"] = "전국"
                    st.rerun()
            with _title_col:
                st.markdown(f"**{_drilldown_city}** — {selected_cat} / {selected_metric_label}")

            if not _dist_df.empty:
                _chart_col = _color_col if _color_col in _dist_df.columns else "opportunity_score"

                # 시군구 GeoJSON이 있으면 choropleth, 없으면 bar chart 폴백
                _sg_features = [
                    f for f in sigungu_geojson.get("features", [])
                    if f.get("properties", {}).get("sido_name") == _drilldown_city
                ] if sigungu_geojson else []

                if _sg_features:
                    _sg_geo = {"type": "FeatureCollection", "features": _sg_features}
                    _geo_names = {f["properties"]["name"] for f in _sg_features}
                    _data_names = set(_dist_df["district"].tolist())

                    # GeoJSON feature → 데이터 district 매핑 (직접 매칭 + prefix 매칭)
                    # 예: GeoJSON '수원시팔달구' ← data '수원시' (prefix match)
                    _geo_to_data: dict[str, str] = {}
                    for _gn in _geo_names:
                        if _gn in _data_names:
                            _geo_to_data[_gn] = _gn
                        else:
                            for _dn in _data_names:
                                if _gn.startswith(_dn):
                                    _geo_to_data[_gn] = _dn
                                    break

                    # 매칭된 GeoJSON feature 행 확장 (부모 district 값을 서브 feature에 복사)
                    if _geo_to_data:
                        _exp_rows = []
                        for _geo_n, _data_n in _geo_to_data.items():
                            _src = _dist_df[_dist_df["district"] == _data_n]
                            if not _src.empty:
                                _r = _src.iloc[0].copy()
                                _r["district"] = _geo_n
                                _exp_rows.append(_r)
                        _dist_matched = pd.DataFrame(_exp_rows) if _exp_rows else _dist_df.copy()
                    else:
                        _dist_matched = _dist_df.copy()

                    fig_d = px.choropleth(
                        _dist_matched,
                        geojson=_sg_geo,
                        locations="district",
                        featureidkey="properties.name",
                        color=_chart_col,
                        color_continuous_scale="Blues",
                        labels={
                            "district": "시/군/구",
                            "opportunity_score": "기회점수", "bid_count": "공고수",
                            "competition_score": "경쟁도", "consumer_fit_score": "소비층 적합도",
                            "hub_score": "물류점수",
                        },
                        hover_name="district",
                        hover_data={_chart_col: True, "bid_count": True},
                    )
                    # 시도별 명시 좌표 범위 (fitbounds 단독으로 zoom 안 되는 경우 보완)
                    _SIDO_BOUNDS: dict[str, tuple] = {
                        "서울특별시":    (126.75, 127.20, 37.42, 37.70),
                        "부산광역시":    (128.80, 129.30, 35.00, 35.38),
                        "대구광역시":    (128.45, 128.85, 35.72, 36.02),
                        "인천광역시":    (126.20, 126.85, 37.28, 37.68),
                        "광주광역시":    (126.75, 127.00, 35.05, 35.30),
                        "대전광역시":    (127.28, 127.60, 36.20, 36.48),
                        "울산광역시":    (129.10, 129.50, 35.40, 35.68),
                        "세종특별자치시": (127.17, 127.38, 36.43, 36.62),
                        "경기도":       (126.55, 127.90, 36.90, 38.30),
                        "강원특별자치도": (127.60, 129.35, 37.05, 38.60),
                        "충청북도":     (127.35, 128.55, 36.05, 37.20),
                        "충청남도":     (126.15, 127.65, 35.90, 37.00),
                        "전라북도":     (126.45, 127.75, 35.20, 36.05),
                        "전라남도":     (125.85, 127.80, 33.90, 35.35),
                        "경상북도":     (128.00, 129.70, 35.68, 37.10),
                        "경상남도":     (127.65, 129.35, 34.60, 35.75),
                        "제주특별자치도": (126.10, 126.98, 33.10, 33.60),
                    }
                    _bnd = _SIDO_BOUNDS.get(_drilldown_city)
                    if _bnd:
                        _lon0, _lon1, _lat0, _lat1 = _bnd
                        fig_d.update_geos(
                            visible=False, bgcolor="rgba(0,0,0,0)",
                            lonaxis={"range": [_lon0, _lon1]},
                            lataxis={"range": [_lat0, _lat1]},
                        )
                    else:
                        fig_d.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
                    fig_d.update_layout(
                        height=625,
                        margin={"r": 0, "t": 10, "l": 0, "b": 0},
                        paper_bgcolor="rgba(0,0,0,0)",
                        coloraxis_showscale=True,
                        coloraxis_colorbar=dict(title=selected_metric_label, len=0.7),
                    )
                    st.plotly_chart(fig_d, use_container_width=True)
                    _unmatched = _data_names - _geo_names
                    if _unmatched and len(_unmatched) < 6:
                        st.caption(f"지도 미매칭 지역 (bar 차트 참고): {', '.join(sorted(_unmatched))}")

                    # 미매칭 지역 bar chart 보조
                    with st.expander("시군구 순위 보기"):
                        _top20 = _dist_df.sort_values(_chart_col, ascending=False).head(TOP_N_MAP)
                        fig_rank = px.bar(
                            _top20.sort_values(_chart_col), x=_chart_col, y="district", orientation="h",
                            color=_chart_col, color_continuous_scale="Blues", height=max(350, len(_top20) * 22),
                        )
                        fig_rank.update_layout(
                            margin={"r": 0, "t": 5, "l": 0, "b": 0},
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            showlegend=False, coloraxis_showscale=False,
                            yaxis={"categoryorder": "total ascending"},
                        )
                        st.plotly_chart(fig_rank, use_container_width=True)
                else:
                    # GeoJSON 없을 때 bar chart 폴백
                    _top20 = _dist_df.head(TOP_N_MAP)
                    _bar_h = max(480, len(_top20) * 26)
                    fig_d = px.bar(
                        _top20, x=_chart_col, y="district", orientation="h",
                        color=_chart_col, color_continuous_scale="Blues",
                        labels={"district": "", "opportunity_score": "기회점수", "bid_count": "공고수"},
                        height=_bar_h,
                    )
                    fig_d.update_layout(
                        margin={"r": 0, "t": 10, "l": 0, "b": 0},
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        showlegend=False, coloraxis_showscale=False,
                        yaxis={"categoryorder": "total ascending"},
                    )
                    st.plotly_chart(fig_d, use_container_width=True)

                # 시군구 선택 (패널 연동)
                st.selectbox(
                    "시군구 상세 보기",
                    _dist_df["district"].tolist(),
                    key="district_select",
                    help="선택 시 우측 패널에 상세 지표 표시",
                )
            else:
                st.info(f"{_drilldown_city}의 {selected_cat} 데이터가 없습니다.")

    # ── 패널 ──────────────────────────────────────────────────────────────────
    with col_panel:
        if _drilldown_city is None:
            if _selected_city:
                # ── 선택 시도 패널 ─────────────────────────────────────────
                st.markdown(f"### {_selected_city}")
                _city_row = (
                    _map_df[_map_df["city"] == _selected_city]
                    if not _map_df.empty else pd.DataFrame()
                )
                if not _city_row.empty:
                    _cr = _city_row.iloc[0]

                    # 판정 배지
                    if "judgment_label" in _map_df.columns:
                        _jlbl = _cr.get("judgment_label", "기회 검토")
                        _jc = _LABEL_COLOR.get(_jlbl, "#78716C")
                        st.markdown(
                            f'<span style="background:{_jc}20;color:{_jc};padding:4px 14px;'
                            f'border-radius:12px;font-size:13px;font-weight:700;">{_jlbl}</span>',
                            unsafe_allow_html=True,
                        )
                        st.markdown("")

                    # 공고 건수 (숫자)
                    st.metric("공고 건수", f"{int(_cr.get('bid_count', 0)):,}건")

                    # 게이지 차트 — 보정 점수 우선, 없으면 기회점수
                    _adj100 = _cr.get("adjusted_score_100")
                    if _adj100 is not None and not pd.isna(_adj100):
                        _metrics_sel = [("보정 점수", float(_adj100), "#0EA5E9", False)]
                    else:
                        _metrics_sel = [("기회점수", _cr.get("opp_score_100") or 0, COLOR_PRIMARY, False)]
                    if "consumer_fit_100" in _map_df.columns:
                        _metrics_sel.append(("소비층 적합도", _cr.get("consumer_fit_100") or 0, COLOR_PURPLE, False))
                    if "competition_100" in _map_df.columns:
                        _metrics_sel.append(("경쟁도", _cr.get("competition_100") or 0, COLOR_BAD, True))
                    _metrics_sel.append(("물류 거점", _cr.get("hub_score") or 0, COLOR_GOOD, False))
                    st.plotly_chart(_make_panel_gauges(_metrics_sel), use_container_width=True, key="gauge_sel")

                st.divider()
                # 해당 시도 품목군 TOP 3
                if not map_summary.empty:
                    _city_top = (
                        map_summary[map_summary["city"] == _selected_city]
                        .sort_values("opportunity_score", ascending=False)
                        .head(3)
                    )
                    if not _city_top.empty:
                        st.markdown("**상위 품목군**")
                        for _ii, _ir in enumerate(_city_top.itertuples()):
                            _lc = COLOR_GOOD if _ii == 0 else COLOR_PRIMARY
                            st.markdown(
                                f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                                f'border-radius:8px;padding:7px 10px;margin-bottom:5px;">'
                                f'<span style="color:{_lc};font-weight:700;">{_ii+1}위</span> '
                                f'<b style="font-size:12px;">{_ir.item_category}</b>'
                                f'<span style="float:right;color:{COLOR_PRIMARY};font-size:12px;font-weight:600;">'
                                f'{_ir.opportunity_score:.1f}점</span></div>',
                                unsafe_allow_html=True,
                            )

                st.divider()
                if st.button("시군구 분석 →", use_container_width=True, type="primary"):
                    st.session_state["map_drilldown_city"] = _selected_city
                    st.session_state["ctx_city"] = _selected_city
                    st.session_state["ctx_cat"] = selected_cat
                    # 이전 drilldown의 district_select 캐시 제거
                    for _k in ("district_select", "_dd_last_city"):
                        st.session_state.pop(_k, None)
                    st.rerun()


            else:
                # ── 전국 요약 패널 ─────────────────────────────────────────
                _panel_title = selected_cat if selected_cat != "전체" else "전체 품목군"
                st.markdown(f"### {_panel_title}")

                if not _map_df.empty and _color_col in _map_df.columns:
                    _top5 = _map_df.sort_values(_color_col, ascending=False).head(5)
                    st.markdown("**전국 상위 시도**")
                    for _i, _row in enumerate(_top5.head(3).itertuples()):
                        _val = getattr(_row, _color_col)
                        _vstr = f"{_val:.1f}" if isinstance(_val, float) else f"{int(_val):,}"
                        _lc = "#16A34A" if _i == 0 else "#2563EB"
                        st.markdown(
                            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                            f'border-radius:8px;padding:8px 12px;margin-bottom:6px;">'
                            f'<span style="color:{_lc};font-weight:700;">{_i+1}위</span> '
                            f'<b>{_row.city}</b>'
                            f'<span style="float:right;color:{COLOR_PRIMARY};font-weight:600;">{_vstr}</span></div>',
                            unsafe_allow_html=True,
                        )

                    st.divider()
                    _cat_bids = int(_map_df["bid_count"].sum()) if "bid_count" in _map_df.columns else 0
                    _cat_opp  = _map_df["opportunity_score"].mean() if "opportunity_score" in _map_df.columns else 0
                    _cat_dist = int(_map_df["district_count"].sum()) if "district_count" in _map_df.columns else 0
                    st.metric("공고 건수", f"{_cat_bids:,}건")
                    st.metric("분석 지역", f"{_cat_dist}개")
                    st.metric("평균 기회점수", f"{_cat_opp:.1f}점")

                    if selected_cat != "전체" and "judgment_label" in _map_df.columns:
                        st.divider()
                        st.markdown("**지역별 판정**")
                        for _lbl, _cnt in _map_df["judgment_label"].value_counts().items():
                            _c = _LABEL_COLOR.get(_lbl, "#78716C")
                            st.markdown(
                                f'<span style="background:{_c}20;color:{_c};padding:2px 10px;'
                                f'border-radius:10px;font-size:12px;font-weight:600;">{_lbl}</span> '
                                f'<span style="font-size:12px;color:#64748B;">{_cnt}개 지역</span>',
                                unsafe_allow_html=True,
                            )


        else:
            # ── 드릴다운 패널 ──────────────────────────────────────────────
            st.markdown(f"### {_drilldown_city}")

            _city_row = (
                _map_df[_map_df["city"] == _drilldown_city]
                if not _map_df.empty else pd.DataFrame()
            )
            if not _city_row.empty:
                _cr = _city_row.iloc[0]
                pa, pb = st.columns(2)
                with pa:
                    st.metric("기회점수", f"{_cr.get('opportunity_score', 0):.1f}점")
                with pb:
                    st.metric("공고 건수", f"{int(_cr.get('bid_count', 0)):,}건")

            if not _dist_df.empty:
                st.divider()
                st.markdown("**상위 시군구**")
                _ds_col = _color_col if _color_col in _dist_df.columns else "opportunity_score"
                for _i, _row in enumerate(_dist_df.head(3).itertuples()):
                    _val = getattr(_row, _ds_col, 0)
                    _vstr = f"{_val:.1f}" if isinstance(_val, float) else f"{int(_val):,}"
                    _lc = "#16A34A" if _i == 0 else "#2563EB"
                    st.markdown(
                        f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                        f'border-radius:8px;padding:8px 12px;margin-bottom:6px;">'
                        f'<span style="color:{_lc};font-weight:700;">{_i+1}위</span> '
                        f'<b>{_row.district}</b>'
                        f'<span style="float:right;color:{COLOR_PRIMARY};font-weight:600;">{_vstr}</span></div>',
                        unsafe_allow_html=True,
                    )

                _sel_dist = st.session_state.get("district_select") or (
                    _dist_df.iloc[0]["district"] if not _dist_df.empty else None
                )
                if _sel_dist and _sel_dist in _dist_df["district"].values:
                    _dr = _dist_df[_dist_df["district"] == _sel_dist].iloc[0]
                    st.divider()
                    st.markdown(f"**{_sel_dist}** 상세")
                    _jlbl = _dr.get("judgment_label", "기회 검토")
                    _jc = _LABEL_COLOR.get(_jlbl, "#78716C")
                    st.markdown(
                        f'<span style="background:{_jc}20;color:{_jc};padding:3px 12px;'
                        f'border-radius:10px;font-size:13px;font-weight:700;">{_jlbl}</span>',
                        unsafe_allow_html=True,
                    )
                    st.metric("공고수", f"{int(_dr.get('bid_count', 0)):,}건")

                    # 드릴다운 패널 게이지 차트
                    def _safe(val, mul=1.0, cap=100.0):
                        v = val if not pd.isna(val) else 0.0
                        return min(float(v) * mul, cap)

                    _opp_raw = _dr.get("opportunity_score") or 0
                    _opp100_d = _safe(_opp_raw, 100.0 / max(_dist_df["opportunity_score"].max(), 1))
                    _metrics_dd = [("기회점수", _opp100_d, COLOR_PRIMARY, False)]
                    if "consumer_fit_score" in _dist_df.columns:
                        _cf100_d = _safe(_dr.get("consumer_fit_score"), 100.0)
                        _metrics_dd.append(("소비층 적합도", _cf100_d, COLOR_PURPLE, False))
                    if "competition_score" in _dist_df.columns:
                        _comp100_d = _safe(_dr.get("competition_score"), 100.0)
                        _metrics_dd.append(("경쟁도", _comp100_d, COLOR_BAD, True))
                    _metrics_dd.append(("물류 점수", _safe(_dr.get("hub_score")), COLOR_GOOD, False))
                    st.plotly_chart(_make_panel_gauges(_metrics_dd), use_container_width=True, key="gauge_dd")
                    st.markdown(
                        "<div style='font-size:10px;color:#64748B;line-height:1.6;margin:-4px 0 4px 0'>"
                        "① <b>기회점수</b>: 공고수·금액·최근성·경쟁도 종합 &nbsp;"
                        "② <b>소비층 적합도</b>: 주소비 연령층 매칭 (0~100) &nbsp;"
                        "③ <b>경쟁도</b>: 개방입찰 비율 — 높을수록 신규진입 유리 &nbsp;"
                        "④ <b>물류점수</b>: 납품 수요 집중도 (0~100)"
                        "</div>",
                        unsafe_allow_html=True,
                    )

                    st.divider()
                    if st.button("지역 분석 탭에서 보기", use_container_width=True):
                        st.session_state["ctx_city"] = _drilldown_city
                        st.session_state["ctx_district"] = _sel_dist
                        st.session_state["ctx_cat"] = selected_cat
                        st.session_state["_nav_tab_idx"] = 2
                        st.rerun()

    # ── 전체 너비 탭 이동 버튼 ────────────────────────────────────────────────
    st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] .stButton > button {
    min-height: 3.4rem !important;
    font-size: 0.85rem !important;
    font-weight: 700 !important;
    white-space: normal !important;
    line-height: 1.4 !important;
}
</style>""", unsafe_allow_html=True)
    # ── 지역 선택 시 안내 배너 ───────────────────────────────────────────────
    _nav_city = _drilldown_city or _selected_city
    if _nav_city:
        _city_label = CITY_LABELS.get(_nav_city, _nav_city)
        st.success(f"**{_city_label}** 선택됨 — 아래 버튼으로 상세 분석 탭으로 이동하세요 ↓", icon="✅")

    _nb1, _nb2, _nb3, _nb4 = st.columns(4)
    _city_suffix = f"\n({CITY_LABELS.get(_nav_city, _nav_city)})" if _nav_city else ""
    with _nb1:
        if st.button(f"📍 지역 분석{_city_suffix}", use_container_width=True, key="pbtn_region"):
            if _nav_city:
                st.session_state["ctx_city"] = _nav_city
            st.session_state["ctx_cat"] = selected_cat
            st.session_state["_nav_tab_idx"] = 2
            st.rerun()
    with _nb2:
        if st.button(f"👥 소비층 적합도{_city_suffix}", use_container_width=True, key="pbtn_consumer"):
            if _nav_city:
                st.session_state["ctx_city"] = _nav_city
            st.session_state["ctx_cat"] = selected_cat
            st.session_state["_nav_tab_idx"] = 5
            st.rerun()
    with _nb3:
        if st.button(f"🏪 경쟁 분석{_city_suffix}", use_container_width=True, key="pbtn_compete"):
            if _nav_city:
                st.session_state["ctx_city"] = _nav_city
            st.session_state["ctx_cat"] = selected_cat
            st.session_state["_nav_tab_idx"] = 6
            st.rerun()
    with _nb4:
        if st.button(f"🚚 물류 거점 분석{_city_suffix}", use_container_width=True, key="pbtn_logistics"):
            if _nav_city:
                st.session_state["ctx_city"] = _nav_city
            st.session_state["ctx_cat"] = selected_cat
            st.session_state["_nav_tab_idx"] = 7
            st.rerun()

    # ── 하단: 전국 집계 요약 ─────────────────────────────────────────────────
    st.markdown(
        "<p style='font-size:12px;color:#94A3B8;margin:8px 0 4px 0'>"
        "📊 전국 집계 (지역·품목 필터 무관 — 100,083건 기준)</p>",
        unsafe_allow_html=True,
    )
    bc1, bc2, bc3 = st.columns(3)

    with bc1:
        st.markdown("**Top 품목군**")
        if not matrix_all.empty:
            top_items = _cached_top_items(matrix_all, n=TOP_N_ITEMS)
            fig_items = px.bar(
                top_items,
                x="bid_count",
                y="item_category",
                orientation="h",
                labels={"bid_count": "공고 수", "item_category": ""},
                color_discrete_sequence=["#3B82F6"],
            )
            fig_items.update_layout(
                height=280,
                margin={"r": 0, "t": 10, "l": 0, "b": 0},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis={"categoryorder": "total ascending"},
            )
            st.plotly_chart(fig_items, use_container_width=True)

    with bc2:
        # 사전 집계 파일 우선 로드 (bid_cleaned_national.csv가 204MB라 git 미추적)
        # outputs/tables/monthly_trend_national.csv는 git에 포함
        if MONTHLY_TREND_PATH.exists():
            trend = pd.read_csv(MONTHLY_TREND_PATH, encoding="utf-8-sig")
            _period_label = (
                f"{trend['연월'].min().replace('-', '.')} ~ {trend['연월'].max().replace('-', '.')}"
                if not trend.empty else ""
            )
        elif not cleaned_all.empty and "posted_date" in cleaned_all.columns:
            trend = _cached_monthly_trend(cleaned_all)
            _dt_series = pd.to_datetime(cleaned_all["posted_date"], errors="coerce")
            _dt_min, _dt_max = _dt_series.min(), _dt_series.max()
            _period_label = (
                f"{_dt_min.strftime('%Y.%m')} ~ {_dt_max.strftime('%Y.%m')}"
                if pd.notna(_dt_min) and pd.notna(_dt_max) else ""
            )
        else:
            trend = pd.DataFrame()
            _period_label = ""

        st.markdown(f"**월별 공고 추이**  <span style='font-size:11px;color:#94A3B8;'>수집 기간: {_period_label}</span>", unsafe_allow_html=True)
        if not trend.empty:
            import datetime as _dt_mod
            _cutoff = (_dt_mod.date.today().replace(day=1) - _dt_mod.timedelta(days=1)).strftime("%Y-%m")
            _trend_cut = trend[(trend["연월"] >= TREND_START_YM) & (trend["연월"] <= _cutoff)]
            _trend_recent = _trend_cut if not _trend_cut.empty else trend.tail(18)
            fig_trend = px.line(
                _trend_recent, x="연월", y="공고 수",
                labels={"연월": "", "공고 수": "공고 수"},
                color_discrete_sequence=["#3B82F6"],
                markers=True,
            )
            fig_trend.update_traces(marker_size=6, line_width=2)
            fig_trend.update_xaxes(tickangle=45)
            fig_trend.update_layout(
                height=300,
                margin={"r": 0, "t": 10, "l": 0, "b": 50},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.caption("공고 원천 데이터(posted_date) 없음")

    with bc3:
        st.markdown("**물류 거점 Top 8**")
        if not matrix_all.empty:
            hub_df = (
                matrix_all.groupby(["city", "district"])
                .agg(score=("opportunity_score", "mean"), bids=("bid_count", "sum"))
                .reset_index()
                .sort_values("score", ascending=False)
                .head(TOP_N_HUB)
            )
            # district가 city와 같거나 포함된 경우(광역시 등) city만 표시
            def _hub_label(row):
                city_short = row["city"][:2]
                dist = row["district"]
                if dist in row["city"] or row["city"] in dist or dist == row["city"][:len(dist)]:
                    return row["city"]
                return f"{city_short} {dist}"
            hub_df["label"] = hub_df.apply(_hub_label, axis=1)
            hub_df["score"] = hub_df["score"].round(1)
            fig_hub = px.bar(
                hub_df, x="score", y="label", orientation="h",
                labels={"score": "기회점수", "label": ""},
                color_discrete_sequence=[COLOR_PURPLE],
            )
            fig_hub.update_layout(
                height=280,
                margin={"r": 0, "t": 10, "l": 0, "b": 0},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis={"categoryorder": "total ascending"},
            )
            st.plotly_chart(fig_hub, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
with tab_search:
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
                    st.warning("분석 데이터가 없습니다.")
                    st.stop()
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
                                    .head(TOP_N_ITEMS)
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
with tab_overview:
    st.markdown(
        "<h2 style='font-size:1.5rem;font-weight:700;margin-bottom:0.2rem;'>"
        "나라장터 공공수요 기반 창업 입지·물류 거점 분석 서비스</h2>",
        unsafe_allow_html=True,
    )
    st.info(
        "조달청 입찰공고를 지역·품목별 공공수요 신호로 해석해, "
        "예비창업자·납품업체·물류사가 데이터 근거로 사업 입지를 탐색하는 분석 플랫폼입니다."
    )

    # ── 핵심 수치 ─────────────────────────────────────────────────────────────
    st.subheader("데이터 규모")
    _ov_c1, _ov_c2, _ov_c3, _ov_c4, _ov_c5 = st.columns(5)
    with _ov_c1:
        _ov_total = len(cleaned) if not cleaned.empty else (len(matrix_all) if not matrix_all.empty else 0)
        st.metric("수집 공고", f"{_ov_total:,}건")
    with _ov_c2:
        _ov_city = (cleaned["city"].nunique() if not cleaned.empty and "city" in cleaned.columns
                    else matrix_all["city"].nunique() if not matrix_all.empty and "city" in matrix_all.columns else 0)
        st.metric("시/도", f"{_ov_city}개")
    with _ov_c3:
        _ov_dist = (cleaned["district"].nunique() if not cleaned.empty and "district" in cleaned.columns
                    else matrix_all["district"].nunique() if not matrix_all.empty and "district" in matrix_all.columns else 0)
        st.metric("시·군·구", f"{_ov_dist}개")
    with _ov_c4:
        _ov_cat = (matrix_all["item_category"].nunique() if not matrix_all.empty and "item_category" in matrix_all.columns
                   else features["item_category"].nunique() if not features.empty else 0)
        st.metric("품목군", f"{_ov_cat}종")
    with _ov_c5:
        st.metric("연계 API", "4개 기관")

    st.caption(f"조달청 {_ov_total:,}건 (수집 기간: {TREND_START_YM} ~ ) · 행안부 인구 · 소상공인 상권정보 · KOSIS 신생기업 생존율")

    st.markdown("---")

    # ── 데이터 파이프라인 ────────────────────────────────────────────────────
    st.subheader("데이터 파이프라인")
    st.code(
        f"""
조달청 입찰공고 API (전국 {_ov_city}개 시/도, {_ov_total:,}건)
  → 공고명 분류 (item_category_detail, {_ov_cat}종)
      1단계: 키워드 규칙 매칭
      2단계: TF-IDF + Logistic Regression ML 분류기 (정확도 98.6%)
      3단계: confidence 미달 → 기타/미분류
  → opportunity_score = 공고수({int(W_CNT*100)}%) + 금액({int(W_AMT*100)}%) + 최근성({int(W_REC*100)}%) + 경쟁도({int(W_COMP*100)}%)
  → bids_per_10k_population (인구 보정)

행안부 연령별 인구 API
  → consumer_fit_score (242개 지역, 품목 주소비층 연령 비중)

소상공인 상권정보 API
  → stores_per_10k (253개 지역, 10개 업종 경쟁 포화도)

KOSIS 신생기업 생존율 API
  → adjusted_score = opportunity_score × (survival_5y/100) × (1 − dissolution_rate)

Gemini AI (gemini-3.1-flash-lite) — 판정 4종
  ① 수요 설명   ② 수요 공백(블루오션/저수요)
  ③ 경쟁 구조   ④ 물류 거점 전략
        """,
        language="text",
    )

    st.markdown("---")

    # ── 주요 지표 설명 ────────────────────────────────────────────────────────
    st.subheader("주요 지표")
    st.markdown(
        """
| 지표 | 계산 방식 | 의미 |
|---|---|---|
| `opportunity_score` | 공고수(40%) + 금액(25%) + 최근성(15%) + 경쟁도(20%) | 지역·품목 공공수요 종합 매력도 |
| `adjusted_score` | opportunity_score × 생존율 × (1 − 소멸률) | KOSIS 신생기업 통계 보정 점수 |
| `competition_score` | 개방입찰 비율 = 1 − 지명경쟁(dsgntCmptYn=Y) 비율 | 신규 진입 용이성 |
| `bids_per_10k_population` | 공고수 ÷ (인구/10,000) | 인구 규모 편향 보정 수요 밀도 |
| `consumer_fit_score` | 주소비층 연령 비중 min-max 정규화 | 인구 구성 기반 소비층 적합도 (0~1) |
| `stores_per_10k` | 점포수 ÷ (인구/10,000) | 업종별 경쟁 포화도 |
| `hub_score` | 품목군 내 bid_count min-max 정규화 (0~100) | 물류 거점 후보 납품 수요 집중도 |
        """
    )

    st.markdown("---")

    # ── 타겟 사용자 ───────────────────────────────────────────────────────────
    st.subheader("서비스 대상")
    _ta1, _ta2, _ta3 = st.columns(3)
    with _ta1:
        st.markdown("**예비창업자**\n\n공공수요 높은 품목·지역 탐색, AI 경쟁 구조 판정으로 진입 판단 근거 확보")
    with _ta2:
        st.markdown("**B2G 납품업체**\n\n영업 거점 우선순위 설정, 지역별 수요 밀도 기반 납품 포트폴리오 최적화")
    with _ta3:
        st.markdown("**물류사 / 3PL**\n\n전국 공공조달 수요 분포 기반 물류 거점 후보 도출 및 커버리지 전략")

    st.markdown("---")

    # ── 한계 ─────────────────────────────────────────────────────────────────
    st.subheader("현재 한계")
    st.warning(
        """
- 공공조달(B2G) 관점만 반영 — 민간 소비수요(B2C)는 소상공인 상권정보 탭에서 보완
- 소비층 적합도는 시/도별 연령 분포 기반 추정값 (실측 시군구 연령 데이터 미확보)
- 기타/미분류 약 9% 잔존 (키워드 규칙 + ML 이후에도 매칭 불가 공고)
- opportunity_score는 공공수요 참고 지표이며 창업 성공 예측값이 아닙니다
- AI 판정은 정량 수치 기반 해석이며 투자·창업 판단 근거가 아닙니다
        """
    )

# ══════════════════════════════════════════════════════════════════════════════
with tab_region:
    _ctx_city_r = st.session_state.get("ctx_city")
    st.header("지역 선택 → 추천 품목")

    if features_all.empty:
        st.warning("분석 데이터가 없습니다. `python -m src.collect.build_seoul_sample`을 실행하세요.")
    else:
        # ctx_city 기준 필터 (전국 지도 탭과 연동)
        _tab_cities = sorted(features_all["city"].dropna().unique().tolist()) if "city" in features_all.columns else []
        _tab_city_labels = [CITY_LABELS.get(c, c) for c in _tab_cities]

        # ctx_city 변경 시 city 위젯 강제 동기화 (pop+index 방식 불안정 → 직접 setValue)
        if st.session_state.get("_region_last_ctx") != _ctx_city_r:
            st.session_state["_region_last_ctx"] = _ctx_city_r
            st.session_state.pop("region_tab_district", None)
            if _ctx_city_r and _ctx_city_r in _tab_cities:
                _lbl_to_set = CITY_LABELS.get(_ctx_city_r, _ctx_city_r)
                if _lbl_to_set in _tab_city_labels:
                    st.session_state["region_tab_city"] = _lbl_to_set
            else:
                st.session_state.pop("region_tab_city", None)

        _ctx_label_r = CITY_LABELS.get(_ctx_city_r, _ctx_city_r) if _ctx_city_r and _ctx_city_r in _tab_cities else (_tab_city_labels[0] if _tab_city_labels else "")
        _default_city_idx = _tab_city_labels.index(_ctx_label_r) if _ctx_label_r in _tab_city_labels else 0
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            sel_city_label = st.selectbox("시/도 선택", _tab_city_labels, index=_default_city_idx, key="region_tab_city")
        sel_city = _tab_cities[_tab_city_labels.index(sel_city_label)] if _tab_cities else None
        # city 변경 시 district 캐시 즉시 제거 (selectbox 옵션 vs 캐시 불일치 방지)
        if st.session_state.get("_region_prev_city") != sel_city_label:
            st.session_state["_region_prev_city"] = sel_city_label
            st.session_state.pop("region_tab_district", None)
        _city_data = features_all[features_all["city"] == sel_city] if sel_city and "city" in features_all.columns else features_all
        with col_f2:
            districts = sorted(_city_data["district"].dropna().unique().tolist())
            # GeoJSON whitelist로 잘못 분류된 타 시도 지역 제거
            _geo_wl = _geo_district_whitelist.get(sel_city, set())
            if _geo_wl:
                _filtered = [d for d in districts if d in _geo_wl]
                if len(_filtered) >= 3:
                    districts = _filtered
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

            if "recommendation_flag" in result.columns and not result.empty:
                # ── bar chart: opportunity_score by item_category ──────────
                _flag_color = {"추천": COLOR_GOOD, "제외": COLOR_BAD, "데이터부족": COLOR_WARN}
                _r_sorted = result.sort_values("opportunity_score")
                _r_sorted["_color"] = _r_sorted["recommendation_flag"].map(_flag_color).fillna("#94A3B8")
                _cf_text = (
                    _r_sorted["consumer_fit_score"].apply(lambda v: f"적합도 {v:.2f}" if pd.notna(v) else "")
                    if "consumer_fit_score" in _r_sorted.columns else [""] * len(_r_sorted)
                )
                fig_reg = go.Figure(go.Bar(
                    x=_r_sorted["opportunity_score"],
                    y=_r_sorted["item_category"],
                    orientation="h",
                    marker_color=_r_sorted["_color"].tolist(),
                    text=_r_sorted["bid_count"].apply(lambda v: f"{int(v)}건"),
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>기회점수: %{x:.2f}<br>공고수: %{text}<extra></extra>",
                ))
                fig_reg.update_layout(
                    height=max(320, len(_r_sorted) * 28),
                    margin={"t": 10, "b": 0, "l": 0, "r": 60},
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis_title="기회점수",
                )
                st.plotly_chart(fig_reg, use_container_width=True)

                # 범례
                _leg_html = "".join(
                    f'<span style="background:{c}20;color:{c};padding:2px 10px;border-radius:10px;'
                    f'font-size:12px;font-weight:600;margin-right:6px;">{l}</span>'
                    for l, c in [("✅ 추천", COLOR_GOOD), ("⚠️ 데이터부족", COLOR_WARN), ("🚫 제외", COLOR_BAD)]
                )
                st.markdown(_leg_html, unsafe_allow_html=True)

                # 상세 테이블은 접어두기
                with st.expander("상세 수치 보기"):
                    show_cols = [c for c in [
                        "item_category", "bid_count", "amount_sum",
                        "opportunity_score", "consumer_fit_score",
                        "recommendation_flag", "bids_per_10k_population",
                    ] if c in result.columns]
                    _disp = result[show_cols].copy()
                    if "amount_sum" in _disp.columns:
                        _disp["amount_sum"] = _disp["amount_sum"].apply(format_won)
                    _disp["recommendation_flag"] = _disp["recommendation_flag"].map({
                        "추천": "✅ 추천", "제외": "🚫 제외", "데이터부족": "⚠️ 데이터부족",
                    }).fillna(_disp["recommendation_flag"])
                    st.dataframe(_disp, use_container_width=True, hide_index=True)

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

                    # AI 판정 — 버튼 클릭 시 표시 (토글 대신)
                    _ai_shortage_key = f"shortage_verdict_{selected}"
                    if _ai_shortage_key not in st.session_state.get("gemini_cache", {}):
                        if st.button("🤖 AI 판정 실행 — 블루오션 vs 저수요", key=f"btn_{_ai_shortage_key}"):
                            with st.spinner("인근 지역 데이터와 비교 분석 중..."):
                                from src.recommendation.gemini_client import build_shortage_verdict, ShortageContext
                                _same_city = features_all[
                                    (features_all["city"] == sel_city) &
                                    (features_all["district"] != selected)
                                ] if "city" in features_all.columns else features_all
                                _total_city_dists = _same_city["district"].nunique()
                                _comparison = []
                                for _item in _shortage_items[:6]:
                                    _item_rows = _same_city[_same_city["item_category"] == _item]
                                    _with_data = (_item_rows["bid_count"] >= MIN_BID_REGION).sum()
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
                                st.rerun()
                    if _ai_shortage_key in st.session_state.get("gemini_cache", {}):
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
            if _overdemand_key not in st.session_state.get("gemini_cache", {}):
                if st.button("🤖 AI 판정 실행 — 레드오션 vs 진입 여지", key=f"btn_{_overdemand_key}"):
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
                        st.rerun()
            if _overdemand_key in st.session_state.get("gemini_cache", {}):
                st.markdown(st.session_state["gemini_cache"][_overdemand_key])

        # AI 공공수요 해석 (Gemini)
        st.subheader("🤖 AI 공공수요 해석")
        st.caption("조달청 입찰공고 데이터 기반 설명입니다. 창업 성공을 예측하지 않으며 공공수요 참고 지표로만 활용하세요.")

        if not top3.empty:
            from src.recommendation.gemini_client import build_demand_summary, DemandContext

            # 현재 지역의 시/도 확인 (ctx_city 우선, 없으면 데이터에서 추출)
            _city_for_district = _ctx_city_r or (
                result["city"].dropna().iloc[0]
                if "city" in result.columns and not result.empty and not result["city"].dropna().empty
                else "전국"
            )

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
with tab_item:
    _ctx_city_i = st.session_state.get("ctx_city")
    st.header("품목 선택 → 적합 지역")

    _features_i = (
        features_all[features_all["city"] == _ctx_city_i].copy()
        if _ctx_city_i and "city" in features_all.columns and not features_all.empty
        else features_all
    )

    if _features_i.empty:
        st.warning("분석 데이터가 없습니다.")
    else:
        items = sorted(_features_i["item_category"].dropna().unique().tolist())
        selected_item = st.selectbox("품목군을 선택하세요", items)

        result = _features_i[_features_i["item_category"] == selected_item].sort_values(
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
            _classified_i = classified[classified["city"] == _ctx_city_i] if (_ctx_city_i and "city" in classified.columns) else classified
            item_classified = _classified_i[_classified_i["item_category_detail"] == selected_item]
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
                        .head(TOP_N_ITEMS)
                    )
                    if not detail_dist.empty:
                        st.markdown("**세부 발주 유형**")
                        st.dataframe(detail_dist.rename(columns={"item_category_detail": "세부 유형"}),
                                     use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
with tab_compare:
    _ctx_city_c = st.session_state.get("ctx_city")
    st.header("두 지역 나란히 비교")
    st.caption("서로 다른 시/도 간 비교도 가능합니다. 예: 전라도 울진군 vs 경상도 구미시")

    if features_all.empty:
        st.warning("분석 데이터가 없습니다.")
    else:
        _cmp_cities = sorted(features_all["city"].dropna().unique().tolist()) if "city" in features_all.columns else []
        _cmp_labels = [CITY_LABELS.get(c, c) for c in _cmp_cities]
        _cmp_default_label = CITY_LABELS.get(_ctx_city_c, _ctx_city_c) if _ctx_city_c and _ctx_city_c in _cmp_cities else (_cmp_labels[0] if _cmp_labels else "")
        _seoul_cmp_idx = _cmp_labels.index(_cmp_default_label) if _cmp_default_label in _cmp_labels else 0

        col_a, col_b = st.columns(2)
        with col_a:
            city_a_label = st.selectbox("A 시/도", _cmp_labels, index=_seoul_cmp_idx, key="cmp_city_a")
            city_a = _cmp_cities[_cmp_labels.index(city_a_label)] if _cmp_cities else None
            if st.session_state.get("_cmp_prev_a") != city_a_label:
                st.session_state["_cmp_prev_a"] = city_a_label
                st.session_state.pop("cmp_dist_a", None)
            dists_a = sorted(features_all[features_all["city"] == city_a]["district"].dropna().unique().tolist()) if city_a else []
            _wl_a = _geo_district_whitelist.get(city_a, set())
            if _wl_a:
                _fa = [d for d in dists_a if d in _wl_a]
                if len(_fa) >= 3:
                    dists_a = _fa
            dist_a = st.selectbox("A 시군구", dists_a, index=0, key="cmp_dist_a")
        with col_b:
            city_b_label = st.selectbox("B 시/도", _cmp_labels, index=_seoul_cmp_idx, key="cmp_city_b")
            city_b = _cmp_cities[_cmp_labels.index(city_b_label)] if _cmp_cities else None
            if st.session_state.get("_cmp_prev_b") != city_b_label:
                st.session_state["_cmp_prev_b"] = city_b_label
                st.session_state.pop("cmp_dist_b", None)
            dists_b = sorted(features_all[features_all["city"] == city_b]["district"].dropna().unique().tolist()) if city_b else []
            _wl_b = _geo_district_whitelist.get(city_b, set())
            if _wl_b:
                _fb = [d for d in dists_b if d in _wl_b]
                if len(_fb) >= 3:
                    dists_b = _fb
            dist_b = st.selectbox("B 시군구", dists_b, index=min(1, len(dists_b) - 1) if dists_b else 0, key="cmp_dist_b")

        # groupby first → 동일 item_category 중복 행 집계 (Series 반환 방지)
        def _agg_compare(df: pd.DataFrame) -> pd.DataFrame:
            if df.empty:
                return df
            agg_cols = {c: "mean" for c in ["opportunity_score", "competition_score"] if c in df.columns}
            agg_cols.update({c: "sum" for c in ["bid_count", "amount_sum"] if c in df.columns})
            return df.groupby("item_category").agg(agg_cols)

        data_a = _agg_compare(features_all[(features_all["city"] == city_a) & (features_all["district"] == dist_a)]) if city_a else pd.DataFrame()
        data_b = _agg_compare(features_all[(features_all["city"] == city_b) & (features_all["district"] == dist_b)]) if city_b else pd.DataFrame()

        all_items = sorted(set(data_a.index) | set(data_b.index))

        rows = []
        for item in all_items:
            score_a = float(data_a.loc[item, "opportunity_score"]) if item in data_a.index else 0
            score_b = float(data_b.loc[item, "opportunity_score"]) if item in data_b.index else 0
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
with tab_consumer:
    _ctx_city_cs = st.session_state.get("ctx_city")
    # ctx_city 변경 시 city/district 위젯 캐시 초기화
    if st.session_state.get("_consumer_last_ctx") != _ctx_city_cs:
        st.session_state["_consumer_last_ctx"] = _ctx_city_cs
        for _k in ("fit_city", "fit_dist"):
            st.session_state.pop(_k, None)
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
                _fit_default_label = CITY_LABELS.get(_ctx_city_cs, _ctx_city_cs) if _ctx_city_cs and _ctx_city_cs in _fit_cities else _fit_city_labels[0]
                _fit_city_default = _fit_city_labels.index(_fit_default_label) if _fit_default_label in _fit_city_labels else 0
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
                if not dist_fit.empty:
                    _cf_sorted = dist_fit.sort_values("consumer_fit_score")
                    fig_cf = go.Figure(go.Bar(
                        x=_cf_sorted["consumer_fit_score"],
                        y=_cf_sorted["item_category"],
                        orientation="h",
                        marker=dict(
                            color=_cf_sorted["consumer_fit_score"],
                            colorscale=[[0, "#EFF6FF"], [1, "#2563EB"]],
                            showscale=False,
                        ),
                        text=_cf_sorted["consumer_fit_score"].apply(lambda v: f"{v:.2f}"),
                        textposition="outside",
                        hovertemplate="<b>%{y}</b><br>소비층 적합도: %{x:.3f}<extra></extra>",
                    ))
                    fig_cf.update_layout(
                        height=max(300, len(_cf_sorted) * 28),
                        margin={"t": 10, "b": 0, "l": 0, "r": 60},
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis={"range": [0, 1.1], "title": "소비층 적합도 (0~1)"},
                    )
                    st.plotly_chart(fig_cf, use_container_width=True)
            with col2:
                st.subheader("해석 기준")
                st.markdown(
                    f"""
**{sel_dist}** 자치구의 연령 인구 구성 기반 점수입니다.

- **소비층 적합도**: 주소비층 연령대가 전체 인구에서 차지하는 비율 기준 정규화 (0~1)

> 의료/복지 → 60대+
> 교육/교구 → 0~20대
> 급식/식자재 → 전 연령
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
                    combined["opportunity_score"] * W_OPP + combined["consumer_fit_score"] * 100 * W_FIT
                ).round(2)
                combined = combined.sort_values("종합 점수", ascending=False)
                # scatter: x=공공수요, y=소비층 적합도, size=공고수
                if len(combined) >= 2:
                    fig_sc = px.scatter(
                        combined.rename(columns={"item_category": "품목군"}),
                        x="opportunity_score", y="consumer_fit_score",
                        size="bid_count", text="품목군",
                        size_max=40,
                        labels={"opportunity_score": "공공수요 점수", "consumer_fit_score": "소비층 적합도"},
                        color="종합 점수",
                        color_continuous_scale="Blues",
                    )
                    fig_sc.update_traces(textposition="top center", textfont_size=10)
                    fig_sc.update_layout(
                        height=380,
                        margin={"t": 20, "b": 20, "l": 0, "r": 0},
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        coloraxis_showscale=False,
                    )
                    # 우상단 영역 강조선
                    fig_sc.add_shape(type="rect",
                        x0=combined["opportunity_score"].quantile(0.5), y0=combined["consumer_fit_score"].median(),
                        x1=combined["opportunity_score"].max() * 1.05, y1=1.05,
                        fillcolor="rgba(22,163,74,0.05)", line=dict(color="#16A34A", width=1, dash="dot"))
                    fig_sc.add_annotation(
                        x=combined["opportunity_score"].max(), y=1.0,
                        text="최우선 후보", showarrow=False, font=dict(color="#16A34A", size=11))
                    st.plotly_chart(fig_sc, use_container_width=True)
                    st.caption("우상단 = 공공수요도 높고 소비층도 맞는 최우선 후보. 원 크기 = 공고 수.")
                else:
                    st.dataframe(combined, use_container_width=True, hide_index=True)

        with tab2:
            cats_fit = sorted(consumer_fit["item_category"].dropna().unique().tolist())
            sel_cat_fit = st.selectbox("품목군을 선택하세요", cats_fit, key="fit_cat")

            cat_fit = consumer_fit[consumer_fit["item_category"] == sel_cat_fit].sort_values(
                "consumer_fit_score", ascending=False
            )

            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(f"'{sel_cat_fit}' 소비층 적합 자치구 순위")
                if not cat_fit.empty:
                    _top_cf = cat_fit.head(TOP_N_MAP).copy()
                    _top_cf["label"] = (
                        _top_cf["city"].str[:2] + " " + _top_cf["district"]
                        if _is_national_fit and "city" in _top_cf.columns
                        else _top_cf["district"]
                    )
                    _top_cf = _top_cf.sort_values("consumer_fit_score")
                    fig_cat = go.Figure(go.Bar(
                        x=_top_cf["consumer_fit_score"],
                        y=_top_cf["label"],
                        orientation="h",
                        marker=dict(
                            color=_top_cf["consumer_fit_score"],
                            colorscale=[[0, "#EFF6FF"], [1, "#7C3AED"]],
                            showscale=False,
                        ),
                        text=_top_cf["consumer_fit_score"].apply(lambda v: f"{v:.2f}"),
                        textposition="outside",
                    ))
                    fig_cat.update_layout(
                        height=max(350, len(_top_cf) * 26),
                        margin={"t": 10, "b": 0, "l": 0, "r": 60},
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis={"range": [0, 1.15], "title": "소비층 적합도 (0~1)"},
                    )
                    st.plotly_chart(fig_cat, use_container_width=True)
                    if len(cat_fit) > 20:
                        st.caption(f"상위 20개 지역 표시 (전체 {len(cat_fit)}개)")
            with col2:
                if not cat_fit.empty:
                    top_fit = cat_fit.iloc[0]
                    st.metric("소비층 가장 많은 지역", top_fit["district"])
                    st.metric("타겟 연령 비중", f"{top_fit['target_age_ratio']:.1%}")
                    st.metric("소비층 적합도", f"{top_fit['consumer_fit_score']:.3f}")

# ══════════════════════════════════════════════════════════════════════════════
with tab_competition:
    _ctx_city_cp = st.session_state.get("ctx_city")
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
        comp_view = competition.copy()

        if _is_national_comp:
            city_count = competition["city"].nunique()
            dist_count = competition["district"].nunique()
            st.caption(f"전국 데이터 ({city_count}개 시/도, {dist_count}개 지역) — 강원특별자치도 제외 (API 미지원)")

            # 도시 selectbox (ctx_city 연동 + 직접 변경 가능)
            _all_cities_cp = sorted(competition["city"].dropna().unique().tolist())
            _cp_default_idx = (
                _all_cities_cp.index(_ctx_city_cp)
                if _ctx_city_cp and _ctx_city_cp in _all_cities_cp
                else 0
            )
            _sel_city_cp = st.selectbox(
                "시/도 선택", ["전국"] + _all_cities_cp,
                index=_cp_default_idx + 1 if _ctx_city_cp and _ctx_city_cp in _all_cities_cp else 0,
                key="comp_city_sel",
            )
            if _sel_city_cp != "전국":
                comp_view = comp_view[comp_view["city"] == _sel_city_cp]
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
                if not filtered.empty:
                    _top_comp = filtered.head(TOP_N_MAP).copy()
                    if _is_national_comp and "city" in _top_comp.columns:
                        _top_comp["label"] = _top_comp["city"].str[:2] + " " + _top_comp["district"]
                    else:
                        _top_comp["label"] = _top_comp["district"]
                    _top_comp = _top_comp.sort_values("stores_per_10k")
                    _mx_s = _top_comp["stores_per_10k"].max() or 1
                    _colors_comp = [
                        f"rgb({int(220 - 180 * v / _mx_s)},{int(38 + 90 * v / _mx_s)},{int(38 + 90 * v / _mx_s)})"
                        for v in _top_comp["stores_per_10k"]
                    ]
                    fig_comp = go.Figure(go.Bar(
                        x=_top_comp["stores_per_10k"],
                        y=_top_comp["label"],
                        orientation="h",
                        marker_color=_colors_comp,
                        text=_top_comp["stores_per_10k"].apply(lambda v: f"{v:.1f}"),
                        textposition="outside",
                    ))
                    fig_comp.update_layout(
                        height=max(350, len(_top_comp) * 26),
                        margin={"t": 10, "b": 0, "l": 0, "r": 60},
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis={"title": "인구 1만명당 점포 수"},
                    )
                    st.plotly_chart(fig_comp, use_container_width=True)
                    if len(filtered) > 20:
                        st.caption(f"상위 20개 지역 표시 (전체 {len(filtered)}개)")
                    with st.expander("상세 수치 보기"):
                        show_cols = (["city", "district"] if _is_national_comp else ["district"]) + ["store_count", "stores_per_10k"]
                        show_cols = [c for c in show_cols if c in filtered.columns]
                        st.dataframe(
                            filtered[show_cols].rename(columns={
                                "city": "시/도", "district": "시/군/구",
                                "store_count": "점포 수", "stores_per_10k": "인구 1만명당 점포",
                            }),
                            use_container_width=True, hide_index=True,
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

            # 전체 업종 비교 히트맵
            _hm_city_sel = st.session_state.get("comp_city_sel", "전국")
            _hm_national = _is_national_comp and (_hm_city_sel == "전국")

            if _hm_national:
                st.subheader("전체 업종 × 시도별 점포 밀도 (인구 1만명당)")
                st.caption("시/도를 선택하면 해당 지역 시군구 단위로 좁혀서 볼 수 있습니다.")
                # 전국 모드: 시도 단위 평균 (253개 지역 → 16개 시도)
                _hm_view = competition.copy() if "city" in competition.columns else comp_view.copy()
                pivot = _hm_view.pivot_table(
                    index="inds_group", columns="city", values="stores_per_10k",
                    aggfunc="mean", fill_value=0,
                ).round(1)
            else:
                st.subheader(f"전체 업종 × 시군구별 점포 밀도 ({_hm_city_sel if not _hm_national else '전국'})")
                pivot = comp_view.pivot_table(
                    index="inds_group", columns="district", values="stores_per_10k", fill_value=0,
                ).round(1)

            if not pivot.empty:
                import plotly.express as _pxhm
                fig_hm = _pxhm.imshow(
                    pivot,
                    labels={"x": "지역", "y": "업종", "color": "점포/1만명"},
                    color_continuous_scale="RdYlGn_r",
                    aspect="auto",
                    text_auto=".1f",
                )
                _hm_col_count = len(pivot.columns)
                fig_hm.update_layout(
                    height=max(320, len(pivot) * 42),
                    margin={"t": 20, "b": max(60, _hm_col_count * 5), "l": 0, "r": 0},
                    paper_bgcolor="rgba(0,0,0,0)",
                    coloraxis_colorbar=dict(title="점포/1만명", len=0.8),
                    xaxis_tickangle=-45,
                )
                fig_hm.update_traces(textfont_size=10 if _hm_col_count <= 20 else 8)
                st.plotly_chart(fig_hm, use_container_width=True)
                st.caption("빨간색 = 경쟁 포화 / 초록색 = 경쟁 여유.")

            st.markdown("---")
            st.subheader("공공수요 vs 경쟁 포화도 비교")
            st.caption("같은 지역에서 공공수요(opportunity_score)는 높고 점포 밀도는 낮은 업종을 찾으세요.")
            if not features.empty:
                bid_cats = sorted(features["item_category"].dropna().unique().tolist())
                sel_cat = st.selectbox("비교할 품목군", bid_cats, key="comp_cat")

                feat_cols = ["city", "district", "bid_count", "opportunity_score"] if "city" in features.columns else ["district", "bid_count", "opportunity_score"]
                feat_cols = [c for c in feat_cols if c in features.columns]
                cat_bids = features[features["item_category"] == sel_cat][feat_cols].copy()
                # 경쟁 분석 탭의 city selectbox 우선, 없으면 ctx_city 사용
                _scatter_city = _sel_city_cp if _sel_city_cp != "전국" else _ctx_city_cp
                if _scatter_city and "city" in cat_bids.columns:
                    cat_bids = cat_bids[cat_bids["city"] == _scatter_city]

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
                    if _is_national_comp and "city" in merged.columns:
                        merged["지역"] = merged["city"].str[:2] + " " + merged["district"]
                    else:
                        merged["지역"] = merged["district"]
                    # 전국 모드: 상위 20개만 표시, 레이블은 top 10만 (나머지 hover)
                    _scatter_national = not _scatter_city
                    if _scatter_national:
                        merged_plot = merged.head(TOP_N_MAP).copy()
                        _top10_labels = set(merged_plot.head(10)["지역"].tolist())
                        merged_plot["_label"] = merged_plot["지역"].apply(lambda x: x if x in _top10_labels else "")
                        _text_col = "_label"
                        st.caption(f"상위 20개 지역 표시 (전체 {len(merged)}개). 시/도 선택 시 해당 지역만 표시됩니다.")
                    else:
                        merged_plot = merged.copy()
                        _text_col = "지역"
                    fig_vs = px.scatter(
                        merged_plot,
                        x="opportunity_score",
                        y="stores_per_10k",
                        size="bid_count",
                        text=_text_col,
                        color="수요↑/경쟁↓ 점수",
                        color_continuous_scale="RdYlGn",
                        hover_name="지역",
                        labels={
                            "opportunity_score": "공공수요 점수",
                            "stores_per_10k": "경쟁 밀도 (점포/1만명)",
                            "bid_count": "공고수",
                        },
                        title=f"'{sel_cat}' 공공수요 vs 경쟁 포화도",
                    )
                    fig_vs.update_traces(textposition="top center", textfont_size=9)
                    # 우하단 = 수요 높고 경쟁 낮음 → 유망
                    _opp_med = merged["opportunity_score"].median()
                    _str_med = merged["stores_per_10k"].median()
                    fig_vs.add_shape(type="rect",
                        x0=_opp_med, y0=0,
                        x1=merged["opportunity_score"].max() * 1.05, y1=_str_med,
                        fillcolor="rgba(22,163,74,0.06)", line=dict(color="#16A34A", width=1, dash="dot"))
                    fig_vs.add_annotation(
                        x=merged["opportunity_score"].max(), y=0,
                        text="유망 지역", showarrow=False, font=dict(color="#16A34A", size=11), yanchor="bottom")
                    fig_vs.update_layout(
                        height=500, margin={"t": 40, "b": 0},
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        coloraxis_showscale=False,
                    )
                    st.plotly_chart(fig_vs, use_container_width=True)
                    st.caption("우하단 (수요↑ 경쟁↓) = 유망 지역. 원 크기 = 공고 수.")
                    with st.expander("상세 수치 보기"):
                        rename_map = {
                            "city": "시/도", "district": "시/군/구",
                            "bid_count": "공공수요 공고수",
                            "opportunity_score": "공공수요 점수",
                            "stores_per_10k": "경쟁 밀도(1만명당)",
                        }
                        st.dataframe(merged.rename(columns=rename_map), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
with tab_logistics:
    _ctx_city_l = st.session_state.get("ctx_city")
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

    # ── 필터 ─────────────────────────────────────────────────────────────────
    _logi_f1, _logi_f2 = st.columns(2)
    with _logi_f1:
        _all_logi_cities = sorted(features_all["city"].dropna().unique().tolist()) if "city" in features_all.columns else []
        _logi_city_labels = ["전국"] + [CITY_LABELS.get(c, c) for c in _all_logi_cities]
        _logi_default = (
            _logi_city_labels.index(CITY_LABELS.get(_ctx_city_l, _ctx_city_l))
            if _ctx_city_l and CITY_LABELS.get(_ctx_city_l, _ctx_city_l) in _logi_city_labels else 0
        )
        _logi_city_sel = st.selectbox("시/도 필터", _logi_city_labels, index=_logi_default, key="logi_city_sel")
    with _logi_f2:
        _logi_cat_options = ["전체 물리적 납품"] + sorted(PHYSICAL_CATEGORIES)
        _logi_cat_sel = st.selectbox("품목 필터", _logi_cat_options, key="logi_cat_sel")

    _logi_city_actual = (
        _all_logi_cities[_logi_city_labels.index(_logi_city_sel) - 1]
        if _logi_city_sel != "전국" and _all_logi_cities else None
    )
    _features_l = (
        features_all[features_all["city"] == _logi_city_actual].copy()
        if _logi_city_actual and "city" in features_all.columns and not features_all.empty
        else features_all.copy() if not features_all.empty else features_all
    )

    if _features_l.empty:
        st.warning("분석 데이터가 없습니다.")
    else:
        # 시/도 × 품목 집계
        _sel_phys_cats = PHYSICAL_CATEGORIES if _logi_cat_sel == "전체 물리적 납품" else {_logi_cat_sel}
        _hub_df = _features_l[_features_l["item_category"].isin(_sel_phys_cats)].copy() if "item_category" in _features_l.columns else pd.DataFrame()

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
                (_city_agg["_bids_score"] * W_HUB_BIDS + _city_agg["_amt_score"] * W_HUB_AMT + _city_agg["_cat_score"] * W_HUB_CAT) * 100
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
                _cat_city.sort_values("bid_count", ascending=False)
                .groupby("item_category", group_keys=False)
                .head(3)
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
with tab_raw:
    st.header("분석 근거 데이터")
    st.caption("이 탭은 분석에 사용된 원천 데이터의 신뢰도와 품질을 확인하는 탭입니다.")

    if cleaned.empty:
        st.info("정제 데이터가 없습니다.")
    else:
        # ── 필터 ─────────────────────────────────────────────────────────────
        _raw_f1, _raw_f2 = st.columns(2)
        with _raw_f1:
            _raw_cities = ["전체"] + sorted(cleaned["city"].dropna().unique().tolist()) if "city" in cleaned.columns else ["전체"]
            _raw_city_def = _raw_cities.index(st.session_state.get("ctx_city") or "전체") if (st.session_state.get("ctx_city") or "전체") in _raw_cities else 0
            _raw_city_sel = st.selectbox("시/도 필터", _raw_cities, index=_raw_city_def, key="raw_city")
        with _raw_f2:
            _raw_base = cleaned if _raw_city_sel == "전체" or "city" not in cleaned.columns else cleaned[cleaned["city"] == _raw_city_sel]
            dist_filter = st.multiselect("자치구 필터 (비우면 전체)", sorted(_raw_base["district"].dropna().unique().tolist()))

        _raw_view = _raw_base if not dist_filter else _raw_base[_raw_base["district"].isin(dist_filter)]

        # ── 데이터 품질 지표 ──────────────────────────────────────────────────
        st.subheader("데이터 품질")
        _rq1, _rq2, _rq3, _rq4, _rq5 = st.columns(5)
        _total_all = len(cleaned)
        _total_sel = len(_raw_view)
        _cat_col = "item_category" if "item_category" in cleaned.columns else None
        _etc_cnt = (_raw_view[_cat_col] == "기타/미분류").sum() if _cat_col else 0
        _etc_rate = _etc_cnt / _total_sel * 100 if _total_sel > 0 else 0
        _classified_rate = 100 - _etc_rate
        with _rq1:
            st.metric("전체 공고", f"{_total_all:,}건")
        with _rq2:
            st.metric("선택 지역 공고", f"{_total_sel:,}건")
        with _rq3:
            st.metric("분류 완료율", f"{_classified_rate:.1f}%")
        with _rq4:
            st.metric("기타/미분류 비율", f"{_etc_rate:.1f}%", delta=f"-{_etc_rate:.1f}%", delta_color="inverse")
        with _rq5:
            _date_col = "posted_date" if "posted_date" in cleaned.columns else None
            if _date_col:
                _dates = pd.to_datetime(_raw_view[_date_col], errors="coerce").dropna()
                _date_range = f"{_dates.min().strftime('%Y.%m')} ~ {_dates.max().strftime('%Y.%m')}" if not _dates.empty else "-"
            else:
                _date_range = "-"
            st.metric("수집 기간", _date_range)

        st.markdown("---")

        # ── 품목군 분포 차트 ──────────────────────────────────────────────────
        if _cat_col:
            st.subheader("품목군별 공고 수 (Top 10)")
            _cat_dist = _raw_view[_cat_col].value_counts().head(10).reset_index()
            _cat_dist.columns = ["품목군", "공고수"]
            _cat_dist = _cat_dist.sort_values("공고수")
            _colors_raw = ["#DC2626" if c == "기타/미분류" else "#2563EB" for c in _cat_dist["품목군"]]
            fig_raw_cat = go.Figure(go.Bar(
                x=_cat_dist["공고수"],
                y=_cat_dist["품목군"],
                orientation="h",
                marker_color=_colors_raw,
                text=_cat_dist["공고수"].apply(lambda v: f"{v:,}건"),
                textposition="outside",
            ))
            fig_raw_cat.update_layout(
                height=350, margin={"t": 10, "b": 0, "l": 0, "r": 80},
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"title": "공고 수"},
            )
            st.plotly_chart(fig_raw_cat, use_container_width=True)
            st.caption("빨간색 = 기타/미분류 (분류 미달). 낮을수록 분류 품질 우수.")

        st.markdown("---")

        # ── 원천 데이터 미리보기 ──────────────────────────────────────────────
        st.subheader("원천 데이터 미리보기")
        show_cols = [c for c in [
            "city", "district", "bid_title", "agency_name",
            "item_category", "estimated_amount", "posted_date",
        ] if c in _raw_view.columns]
        display = _raw_view[show_cols].head(RAW_PREVIEW).copy()
        if "estimated_amount" in display.columns:
            display["estimated_amount"] = display["estimated_amount"].apply(format_won)
        st.caption(f"최대 500건 표시 (전체 {_total_sel:,}건)")
        st.dataframe(display, use_container_width=True, hide_index=True)

        # ── 다운로드 ──────────────────────────────────────────────────────────
        _dl_data = _raw_view[show_cols].copy()
        if "estimated_amount" in _dl_data.columns:
            _dl_data["estimated_amount"] = _dl_data["estimated_amount"].apply(format_won)
        st.download_button(
            label="CSV 다운로드",
            data=_dl_data.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name=f"procurement_data_{_raw_city_sel}.csv",
            mime="text/csv",
        )

    if REPORT_PATH.exists():
        with st.expander("자동 생성 요약 리포트"):
            st.markdown(REPORT_PATH.read_text(encoding="utf-8"))
