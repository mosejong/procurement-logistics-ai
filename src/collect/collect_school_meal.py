"""
aT 학교급식 낙찰/입찰 현황 수집 + 지역별 요약 (전 연도)

역할:
    연도별 스냅샷(입찰 5개 / 낙찰 3개)을 합산 수집해
    구매사명(학교명)에서 시도를 추출하고 지역별로 집계합니다.

    입찰 = 공공기관의 구매 의향 (예정 수요)
    낙찰 = 실제 계약 완료 (확정 수요)
    → "공고=의사 / 계약=실측" 2단 구조의 급식 버전

출력:
    outputs/tables/school_meal_bid_summary.csv       — 입찰 지역별 집계
    outputs/tables/school_meal_award_summary.csv     — 낙찰 지역별 집계
    outputs/tables/school_meal_contract_summary.csv  — 통합 요약

실행:
    python -m src.collect.collect_school_meal              # 전 연도
    python -m src.collect.collect_school_meal --latest     # 최신 연도만 (빠름)
    python -m src.collect.collect_school_meal --sample     # 각 URL 100건만 (테스트)
"""

import argparse
from pathlib import Path

import pandas as pd

from src.api.school_meal_api import (
    AWARD_URLS, BID_URLS, URL_AWARD, URL_BID, fetch_all, extract_sido, load_neis_cache
)

ROOT = Path(__file__).parent.parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"


def _fetch_all_years(url_map: dict[str, str], label: str,
                     max_pages: int, per_page: int) -> pd.DataFrame:
    """연도별 URL dict를 순서대로 수집해 중복 제거 후 합산."""
    frames = []
    for year, url in url_map.items():
        print(f"  [{year}] {url.split('uddi:')[1][:8]}...")
        df = fetch_all(url, max_pages=max_pages, per_page=per_page)
        if not df.empty:
            df["_snapshot_year"] = year
            frames.append(df)
            print(f"    -> {len(df):,}건")
        else:
            print(f"    -> 0건 (스킵)")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # 중복 제거: 공고번호 또는 전자입찰일련번호 기준
    dedup_col = None
    for col in ["공고번호", "전자입찰일련번호"]:
        if col in combined.columns:
            dedup_col = col
            break
    if dedup_col:
        before = len(combined)
        combined = combined.drop_duplicates(subset=[dedup_col])
        print(f"  중복 제거: {before:,} -> {len(combined):,}건")

    return combined.reset_index(drop=True)


def _summarize_by_city(df: pd.DataFrame, name_col: str = "구매사명",
                       neis_cache: dict | None = None) -> pd.DataFrame:
    """구매사명에서 시도 추출 후 집계."""
    df = df.copy()
    df["city"] = df[name_col].apply(lambda x: extract_sido(x, neis_cache))

    grp = df.groupby("city")
    summary = grp.agg(count=("city", "count")).reset_index()
    summary["school_count"] = grp[name_col].nunique().values

    total = len(df)
    other = len(df[df["city"] == "기타"])
    print(f"  지역 매핑: {total - other:,}/{total:,}건 ({(total-other)/total*100:.1f}%) 성공, 기타 {other:,}건")

    return summary.sort_values("count", ascending=False).reset_index(drop=True)


def run(sample: bool = False, latest_only: bool = False) -> None:
    per_page = 100 if sample else 1000
    max_pages = 1 if sample else 9999

    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    # NEIS 캐시 로드 (build_school_city_map.py 결과)
    neis_cache = load_neis_cache()
    print(f"NEIS 캐시: {len(neis_cache):,}건 로드")

    bid_urls  = {"20241231": URL_BID}  if latest_only else BID_URLS
    award_urls = {"20241231": URL_AWARD} if latest_only else AWARD_URLS

    # ── 1. 입찰 수집 ──────────────────────────────────────────────────
    print(f"\n[1/3] 학교급식 입찰 현황 수집 ({'최신만' if latest_only else '전 연도'})...")
    df_bid = _fetch_all_years(bid_urls, "입찰", max_pages, per_page)
    print(f"  합산: {len(df_bid):,}건")

    bid_summary = _summarize_by_city(df_bid, "구매사명", neis_cache)
    bid_summary = bid_summary.rename(columns={"count": "bid_count", "school_count": "school_bid_count"})
    bid_path = TABLES_DIR / "school_meal_bid_summary.csv"
    bid_summary.to_csv(bid_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {bid_path.name}")

    # ── 2. 낙찰 수집 ──────────────────────────────────────────────────
    print(f"\n[2/3] 학교급식 낙찰 현황 수집 ({'최신만' if latest_only else '전 연도'})...")
    df_award = _fetch_all_years(award_urls, "낙찰", max_pages, per_page)
    print(f"  합산: {len(df_award):,}건")

    award_summary = _summarize_by_city(df_award, "구매사명", neis_cache)
    award_summary = award_summary.rename(columns={"count": "award_count", "school_count": "school_award_count"})
    award_path = TABLES_DIR / "school_meal_award_summary.csv"
    award_summary.to_csv(award_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {award_path.name}")

    # ── 3. 통합 요약 ──────────────────────────────────────────────────
    print("\n[3/3] 통합 요약 생성...")
    merged = bid_summary.merge(award_summary, on="city", how="outer").fillna(0)
    merged["bid_count"]   = merged["bid_count"].astype(int)
    merged["award_count"] = merged["award_count"].astype(int)

    merged["award_conversion_rate"] = (
        merged["award_count"] / merged["bid_count"].replace(0, float("nan"))
    ).round(3).fillna(0)

    out_path = TABLES_DIR / "school_meal_contract_summary.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {out_path.name}")

    result_path = TABLES_DIR / "school_meal_result.txt"
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(merged.to_string(index=False))

    with open(result_path, encoding="utf-8") as f:
        print(f.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample",  action="store_true", help="각 URL 100건만 수집 (테스트)")
    parser.add_argument("--latest",  action="store_true", help="최신 연도 URL만 수집 (빠름)")
    args = parser.parse_args()
    run(sample=args.sample, latest_only=args.latest)
