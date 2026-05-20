"""
낙찰/계약 요약 집계 — "공고=의사 / 계약=실측" 2단 구조

기존 award_api.py를 기반으로 시도 단위 낙찰 데이터를 수집하고,
입찰공고 데이터와 결합해 demand_confidence_score를 산출합니다.

출력: outputs/tables/award_summary_national.csv
컬럼: city, item_category, notice_count, award_count, notice_amount_sum,
       award_amount_sum, contract_conversion_rate, avg_award_rate,
       demand_confidence_score
"""

import argparse
from pathlib import Path

import pandas as pd

from src.api.award_api import get_award_list, clean_award_data
from src.config.regions import REGIONS
from src.config.settings import OUTPUT_TABLE_DIR
from src.preprocess.classify_agency import apply_classifications

ROOT = Path(__file__).parent.parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"
OUT_PATH = TABLES_DIR / "award_summary_national.csv"
MATRIX_PATH = TABLES_DIR / "opportunity_matrix_national.csv"


def _collect_city_awards(city: str, city_label: str, days_back: int = 730) -> pd.DataFrame:
    """시도 단위로 낙찰 데이터 수집 (30일 window × 기간)."""
    from datetime import datetime, timedelta

    end = datetime.now()
    start = end - timedelta(days=days_back)
    frames = []
    cursor = start

    while cursor < end:
        window_end = min(cursor + timedelta(days=30), end)
        start_str = cursor.strftime("%Y%m%d0000")
        end_str = window_end.strftime("%Y%m%d2359")

        for page in range(1, 6):
            df = get_award_list(
                page_no=page,
                num_of_rows=100,
                start_date=start_str,
                end_date=end_str,
                dminstt_nm=city_label,
            )
            if df.empty:
                break
            frames.append(df)

        cursor = window_end + timedelta(days=1)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True).drop_duplicates()
    result["_source_city"] = city
    return result


def _normalize(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


def build(cities: list[str] | None = None) -> None:
    target_cities = cities or list(REGIONS.keys())

    # 시도 단축명 매핑 (API 쿼리용)
    city_labels: dict[str, str] = {
        "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
        "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
        "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
        "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
        "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
        "경상남도": "경남", "제주특별자치도": "제주",
    }

    all_frames = []
    for city in target_cities:
        label = city_labels.get(city, city[:2])
        print(f"[낙찰] {city} 수집 중...")
        df = _collect_city_awards(city, label)
        if not df.empty:
            df = clean_award_data(df)
            all_frames.append(df)
            print(f"  >> {len(df)}건")
        else:
            print(f"  >> 데이터 없음")

    if not all_frames:
        print("[경고] 낙찰 데이터 수집 실패. API 키 및 엔드포인트 확인 필요.")
        return

    awards = pd.concat(all_frames, ignore_index=True)

    # 공고명 기반 품목 분류
    if "bidNtceDtls" in awards.columns:
        awards = apply_classifications(awards, text_col="bidNtceDtls")
    elif "ntceInsttNm" in awards.columns:
        awards = apply_classifications(awards, text_col="ntceInsttNm")

    if "item_category" not in awards.columns:
        awards["item_category"] = "기타/미분류"

    # 낙찰금액 컬럼 통일
    amt_col = "sucsfbidAmt" if "sucsfbidAmt" in awards.columns else None

    agg: dict = {
        "award_count": ("bidNtceNo", "count") if "bidNtceNo" in awards.columns
                       else ("item_category", "count"),
    }
    if amt_col:
        agg["award_amount_sum"] = (amt_col, "sum")
        agg["avg_award_rate"] = ("drwtPcnt", "mean") if "drwtPcnt" in awards.columns \
                                else (amt_col, "mean")

    city_col = "_source_city" if "_source_city" in awards.columns else "city"
    summary = (
        awards.groupby([city_col, "item_category"])
        .agg(**agg)
        .reset_index()
        .rename(columns={city_col: "city"})
    )

    # 입찰공고 데이터 결합
    if MATRIX_PATH.exists():
        matrix = pd.read_csv(MATRIX_PATH, encoding="utf-8-sig")
        bid_agg = (
            matrix.groupby(["city", "item_category"])
            .agg(notice_count=("bid_count", "sum"), notice_amount_sum=("amount_sum", "sum"))
            .reset_index()
        )
        summary = bid_agg.merge(summary, on=["city", "item_category"], how="left")
        summary["award_count"] = summary["award_count"].fillna(0).astype(int)
        if "award_amount_sum" in summary.columns:
            summary["award_amount_sum"] = summary["award_amount_sum"].fillna(0)

        # 계약 전환율: 낙찰 건수 / 공고 건수
        summary["contract_conversion_rate"] = (
            summary["award_count"] / summary["notice_count"].replace(0, float("nan"))
        ).round(4).fillna(0)

    # demand_confidence_score (MVP 가중치 — 향후 실제 낙찰률로 보정 예정)
    # 0.5 * notice + 0.3 * award_count + 0.2 * award_amount
    n_norm = _normalize(summary.get("notice_count", pd.Series([0])))
    a_norm = _normalize(summary.get("award_count", pd.Series([0])))
    am_norm = _normalize(summary.get("award_amount_sum", pd.Series([0])))

    summary["demand_confidence_score"] = (
        0.5 * n_norm + 0.3 * a_norm + 0.2 * am_norm
    ).round(4)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] {OUT_PATH.name} ({len(summary):,}행)")
    print(f"     city: {summary['city'].nunique()} / item_category: {summary['item_category'].nunique()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="낙찰/계약 요약 집계")
    parser.add_argument("--cities", nargs="+", help="수집할 시도 목록")
    args = parser.parse_args()
    build(cities=args.cities)
