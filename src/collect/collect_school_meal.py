"""
aT 학교급식 낙찰/입찰 현황 수집 + 지역별 요약

역할:
    낙찰(165,461건)과 입찰(83,963건) 데이터를 수집해
    구매사명(학교명)에서 시도를 추출하고 지역별로 집계합니다.

    입찰 = 공공기관의 구매 의향 (예정 수요)
    낙찰 = 실제 계약 완료 (확정 수요)
    → "공고=의사 / 계약=실측" 2단 구조의 급식 버전

출력:
    outputs/tables/school_meal_bid_summary.csv   — 입찰 지역별 집계
    outputs/tables/school_meal_award_summary.csv — 낙찰 지역별 집계
    outputs/tables/school_meal_contract_summary.csv — 통합 요약

실행:
    python -m src.collect.collect_school_meal
    python -m src.collect.collect_school_meal --sample   # 샘플 100건만
"""

import argparse
from pathlib import Path

import pandas as pd

from src.api.school_meal_api import (
    URL_AWARD, URL_BID, fetch_all, extract_sido
)

ROOT = Path(__file__).parent.parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"


def _summarize_by_city(df: pd.DataFrame, name_col: str = "구매사명") -> pd.DataFrame:
    """구매사명에서 시도 추출 후 집계."""
    df = df.copy()
    df["city"] = df[name_col].apply(extract_sido)

    grp = df.groupby("city")
    summary = grp.agg(count=("city", "count")).reset_index()
    summary["school_count"] = grp[name_col].nunique().values

    # 기타 비율 표시
    total = len(df)
    other = len(df[df["city"] == "기타"])
    print(f"  지역 매핑: {total - other:,}/{total:,}건 ({(total-other)/total*100:.1f}%) 성공, 기타 {other:,}건")

    return summary.sort_values("count", ascending=False).reset_index(drop=True)


def run(sample: bool = False) -> None:
    per_page = 100 if sample else 1000
    max_pages = 1 if sample else 200

    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 입찰 수집 ──────────────────────────────────────────────────
    print("[1/3] 학교급식 입찰 현황 수집...")
    df_bid = fetch_all(URL_BID, max_pages=max_pages, per_page=per_page)
    print(f"  수집: {len(df_bid):,}건")

    bid_summary = _summarize_by_city(df_bid, "구매사명")
    bid_summary = bid_summary.rename(columns={"count": "bid_count", "school_count": "school_bid_count"})
    bid_path = TABLES_DIR / "school_meal_bid_summary.csv"
    bid_summary.to_csv(bid_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {bid_path.name}")

    # ── 2. 낙찰 수집 ──────────────────────────────────────────────────
    print("\n[2/3] 학교급식 낙찰 현황 수집...")
    df_award = fetch_all(URL_AWARD, max_pages=max_pages, per_page=per_page)
    print(f"  수집: {len(df_award):,}건")

    award_summary = _summarize_by_city(df_award, "구매사명")
    award_summary = award_summary.rename(columns={"count": "award_count", "school_count": "school_award_count"})
    award_path = TABLES_DIR / "school_meal_award_summary.csv"
    award_summary.to_csv(award_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {award_path.name}")

    # ── 3. 통합 요약 ──────────────────────────────────────────────────
    print("\n[3/3] 통합 요약 생성...")
    merged = bid_summary.merge(award_summary, on="city", how="outer").fillna(0)
    merged["bid_count"]   = merged["bid_count"].astype(int)
    merged["award_count"] = merged["award_count"].astype(int)

    # 낙찰 전환율 (낙찰 / 입찰)
    merged["award_conversion_rate"] = (
        merged["award_count"] / merged["bid_count"].replace(0, float("nan"))
    ).round(3).fillna(0)

    out_path = TABLES_DIR / "school_meal_contract_summary.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {out_path.name}")

    # 결과 출력
    with open(f"{TABLES_DIR}/school_meal_result.txt", "w", encoding="utf-8") as f:
        f.write(merged.to_string(index=False))

    result_path = TABLES_DIR / "school_meal_result.txt"
    with open(result_path, encoding="utf-8") as f:
        print(f.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true", help="100건만 수집 (테스트용)")
    args = parser.parse_args()
    run(sample=args.sample)
