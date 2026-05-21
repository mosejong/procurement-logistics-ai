"""
map_item_city_summary.csv 생성 스크립트

품목군 × 시도 단위로 지도 색상과 우측 패널에 필요한 정량 지표를 선처리합니다.
AI 문장은 포함하지 않습니다 (on-demand 생성 방식).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"

MATRIX_PATH = TABLES_DIR / "opportunity_matrix_national.csv"
CONSUMER_FIT_PATH = TABLES_DIR / "national_consumer_fit.csv"
SURVIVAL_PATH = TABLES_DIR / "kosis_survival_rate.csv"
OUT_PATH = TABLES_DIR / "map_item_city_summary.csv"

# 조달 품목군 → KOSIS 산업 분류 매핑 (생존율 조인용)
PROCUREMENT_TO_KOSIS: dict[str, str] = {
    "IT장비/전산":    "IT/전자",
    "전문용역/컨설팅": "IT/전자",
    "건설/공사":      "건설/시설",
    "시설유지보수":   "건설/시설",
    "조경/녹지관리":  "건설/시설",
    "의료/복지용품":  "의료/복지",
    "교육물품/교구":  "교육/문화",
    "행사/운영용역":  "교육/문화",
    "급식/식자재":    "식품/농업",
    "급수/전기/설비": "환경/에너지",
    "청소/환경미화":  "환경/에너지",
    "폐기물/환경":    "환경/에너지",
    "방역/소독":      "환경/에너지",
    "경비/보안":      "기타",
    "보험/금융":      "기타",
    "사무용품/소모품": "기타",
    "인쇄/홍보물":    "기타",
    "차량/운송":      "기타",
    "기타/미분류":    "기타",
}

OPP_HIGH = 28.4      # 75th percentile → 고기회 지역
COMP_LOW  = 0.5      # < 0.5 → 경쟁 주의 (지명경쟁 비율 높음)
CF_HIGH   = 0.6      # > 0.6 → 소비층 적합
HUB_HIGH  = 70.0     # hub_score (normalized) >= 70 → 물류 거점 후보
MIN_BIDS  = 10       # < 10 → 데이터 부족


def _judgment(row: pd.Series, opp_q75: float) -> str:
    if row["bid_count"] < MIN_BIDS:
        return "데이터 부족"
    if row["opportunity_score"] >= opp_q75:
        return "고기회 지역"
    if row.get("competition_score", 1.0) < COMP_LOW:
        return "경쟁 주의"
    if row.get("consumer_fit_score", 0.0) > CF_HIGH:
        return "소비층 적합"
    if row.get("hub_score", 0.0) >= HUB_HIGH:
        return "물류 거점 후보"
    return "기회 검토"


def build() -> None:
    if not MATRIX_PATH.exists():
        raise FileNotFoundError(f"매트릭스 파일 없음: {MATRIX_PATH}")

    from src.config.category_map import MATRIX_TO_DISPLAY

    matrix = pd.read_csv(MATRIX_PATH, encoding="utf-8-sig")

    # ── 0. 카테고리명 통합 (matrix taxonomy → display taxonomy) ─────────────
    matrix["item_category"] = matrix["item_category"].map(MATRIX_TO_DISPLAY).fillna(matrix["item_category"])

    # ── 1. 품목군 × 시도 집계 (rename 후 merged 카테고리 재집계) ────────────
    agg_spec: dict[str, tuple] = {}
    for col, func in [
        ("opportunity_score", "mean"),
        ("competition_score", "mean"),
        ("bid_count", "sum"),
        ("amount_sum", "sum"),
    ]:
        if col in matrix.columns:
            agg_spec[col] = (col, func)
    if "district" in matrix.columns:
        agg_spec["district_count"] = ("district", "nunique")

    summary = (
        matrix.groupby(["item_category", "city"])
        .agg(**agg_spec)
        .reset_index()
    )

    # ── 2. 소비층 적합도 조인 ──────────────────────────────────────────────
    if CONSUMER_FIT_PATH.exists():
        cf = pd.read_csv(CONSUMER_FIT_PATH, encoding="utf-8-sig")
        if {"item_category", "city", "consumer_fit_score"}.issubset(cf.columns):
            cf_city = (
                cf.groupby(["item_category", "city"])["consumer_fit_score"]
                .mean()
                .reset_index()
            )
            summary = summary.merge(cf_city, on=["item_category", "city"], how="left")
        elif {"city", "consumer_fit_score"}.issubset(cf.columns):
            cf_city = cf.groupby("city")["consumer_fit_score"].mean().reset_index()
            summary = summary.merge(cf_city, on="city", how="left")

    # ── 3. hub_score: 품목군 내 bid_count 정규화 (0~100) ─────────────────
    def _normalize_bids(grp: pd.DataFrame) -> pd.Series:
        mn, mx = grp["bid_count"].min(), grp["bid_count"].max()
        if mx == mn:
            return pd.Series(50.0, index=grp.index)
        return (grp["bid_count"] - mn) / (mx - mn) * 100

    summary["hub_score"] = (
        summary.groupby("item_category", group_keys=False)
        .apply(_normalize_bids)
        .round(1)
    )

    # ── 4. 품목군 내 기회점수 순위 ───────────────────────────────────────
    summary["rank_in_item"] = (
        summary.groupby("item_category")["opportunity_score"]
        .rank(ascending=False, method="min")
        .astype(int)
    )

    # ── 5. 판정 라벨 ─────────────────────────────────────────────────────
    opp_q75 = summary["opportunity_score"].quantile(0.75)
    summary["judgment_label"] = summary.apply(
        lambda r: _judgment(r, opp_q75), axis=1
    )

    # ── 6. KOSIS 생존율 조인 → adjusted_score 계산 ───────────────────────
    if SURVIVAL_PATH.exists():
        surv = pd.read_csv(SURVIVAL_PATH, encoding="utf-8-sig")

        # 조달 품목군 → KOSIS 분류 변환 후 조인
        summary["_kosis_cat"] = summary["item_category"].map(PROCUREMENT_TO_KOSIS).fillna("기타")

        surv_sub = surv[surv["item_category"] != "전체"][
            ["city", "item_category", "survival_5y", "dissolution_rate"]
        ].rename(columns={"item_category": "_kosis_cat"})

        summary = summary.merge(surv_sub, on=["city", "_kosis_cat"], how="left")

        # 폴백: city 전체 평균으로 NaN 채우기
        surv_overall = (
            surv[surv["item_category"] == "전체"][["city", "survival_5y", "dissolution_rate"]]
            .rename(columns={"survival_5y": "_s5_all", "dissolution_rate": "_dr_all"})
        )
        summary = summary.merge(surv_overall, on="city", how="left")
        summary["survival_5y"] = summary["survival_5y"].fillna(summary["_s5_all"])
        summary["dissolution_rate"] = summary["dissolution_rate"].fillna(summary["_dr_all"])
        summary.drop(columns=["_s5_all", "_dr_all", "_kosis_cat"], errors="ignore", inplace=True)

        # adjusted_score = opportunity_score × (survival_5y/100) × (1 - dissolution_rate)
        s5 = summary["survival_5y"].fillna(60.0) / 100
        dr = summary["dissolution_rate"].fillna(0.10)
        summary["adjusted_score"] = (summary["opportunity_score"] * s5 * (1 - dr)).round(2)

        _amn, _amx = summary["adjusted_score"].min(), summary["adjusted_score"].max()
        if _amx > _amn:
            summary["adjusted_score_100"] = (
                (summary["adjusted_score"] - _amn) / (_amx - _amn) * 100
            ).round(1)
        else:
            summary["adjusted_score_100"] = 50.0

    # ── 7. 0~100 정규화 컬럼 추가 ────────────────────────────────────────
    _mn = summary["opportunity_score"].min()
    _mx = summary["opportunity_score"].max()
    if _mx > _mn:
        summary["opp_score_100"] = ((summary["opportunity_score"] - _mn) / (_mx - _mn) * 100).round(1)
    else:
        summary["opp_score_100"] = 50.0

    if "consumer_fit_score" in summary.columns:
        summary["consumer_fit_100"] = (summary["consumer_fit_score"] * 100).round(1)
    if "competition_score" in summary.columns:
        summary["competition_100"] = (summary["competition_score"] * 100).round(1)
    # hub_score already 0~100

    # ── 8. 반올림 및 저장 ────────────────────────────────────────────────
    for col in ["opportunity_score", "competition_score", "consumer_fit_score", "hub_score", "adjusted_score"]:
        if col in summary.columns:
            summary[col] = summary[col].round(2)
    if "amount_sum" in summary.columns:
        summary["amount_sum"] = summary["amount_sum"].round(0).astype("Int64")

    summary.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] saved: {OUT_PATH.name} ({len(summary):,} rows)")
    print(f"     item_cat: {summary['item_category'].nunique()} / city: {summary['city'].nunique()}")
    print(f"     judgment:\n{summary['judgment_label'].value_counts().to_string()}")


if __name__ == "__main__":
    build()
