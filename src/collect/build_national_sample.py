"""
전국 시/도별 조달청 입찰공고 수집

역할:
    전국 17 시/도 단위로 조달청 나라장터 입찰공고를 수집합니다.
    기존 build_seoul_sample.py의 수집 로직을 전국으로 확장한 버전입니다.

주요 함수:
    collect_bids_for_city_bulk() - 시/도 단위 일괄 수집 (구 단위보다 API 호출 수 15배 절감)
    collect_by_cities()          - 지정된 시/도 목록 수집
    main()                       - 전국 수집 → 정제 → 매트릭스 → 저장 전체 실행

수집 전략:
    - dminsttNm(수요기관명)에 시/도 단축명(예: "부산")을 넣어 시/도 단위로 일괄 수집합니다.
    - 구 단위 루프(264회) 대신 시/도 단위(17회) 쿼리로 API 할당량을 약 15배 절감합니다.
    - district는 수집 후 clean_bid_data의 _extract_district가 기관명/공고명 텍스트에서 추론합니다.
    - 전체 수집은 시간이 걸리므로 --cities 옵션으로 시/도를 선택해 실행할 수 있습니다.

실행 예시:
    python -m src.collect.build_national_sample                        # 전국 전체
    python -m src.collect.build_national_sample --cities 부산광역시 대구광역시
    python -m src.collect.build_national_sample --cities 서울특별시    # 서울만
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.api.procurement_api import get_bid_list
from src.config.regions import CITY_LABELS, REGIONS
from src.config.settings import DATA_PROCESSED_DIR, DATA_RAW_DIR, OUTPUT_TABLE_DIR
from src.features.build_features import build_feature_table
from src.features.build_opportunity_matrix import build_opportunity_matrix, summarize_top_items_by_district
from src.preprocess.clean_bid_data import clean_bid_data
from src.utils.file_handler import ensure_dir, save_csv


def _date_windows(days_back: int = 730, window_days: int = 30) -> list[tuple[str, str]]:
    """API 조회 범위 초과를 피하려고 전체 기간을 30일 단위로 쪼갭니다."""
    end = datetime.now()
    start = end - timedelta(days=days_back)
    windows = []
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=window_days), end)
        windows.append((
            cursor.strftime("%Y%m%d0000"),
            window_end.strftime("%Y%m%d2359"),
        ))
        cursor = window_end + timedelta(days=1)
    return windows


def collect_bids_for_city_bulk(
    city: str,
    pages_per_window: int = 5,
) -> pd.DataFrame:
    """
    시/도 단위 일괄 수집 (dminsttNm=시/도 단축명).

    구 단위 루프(예: 서울 25회) 대신 단축명(예: "서울") 한 번으로 조회합니다.
    API 호출 수를 약 15배 절감해 일일 할당량 소진을 방지합니다.
    district는 clean_bid_data의 _extract_district가 기관명 텍스트에서 추론합니다.
    """
    search_name = CITY_LABELS.get(city, city[:2])
    frames = []
    for start_date, end_date in _date_windows():
        window_count = 0
        for page_no in range(1, pages_per_window + 1):
            df = get_bid_list(
                page_no=page_no,
                num_of_rows=100,
                start_date=start_date,
                end_date=end_date,
                extra_params={"dminsttNm": search_name},
                verbose=False,
            )
            if df.empty:
                break
            frames.append(df)
            window_count += len(df)
        if window_count:
            print(f"    {start_date[:8]}~{end_date[:8]}: {window_count}건")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True).drop_duplicates()
    result["_source_city"] = city
    return result


def collect_by_cities(
    cities: list[str] | None = None,
    pages_per_window: int = 5,
) -> pd.DataFrame:
    """
    지정된 시/도 목록을 시/도 단위 bulk 쿼리로 수집합니다.
    cities=None이면 전국 전체를 수집합니다.
    """
    target_cities = cities or list(REGIONS.keys())
    all_frames = []

    for city in target_cities:
        label = CITY_LABELS.get(city, city)
        print(f"\n[{label}] 시/도 단위 수집 시작 (dminsttNm={CITY_LABELS.get(city, city[:2])})")

        df = collect_bids_for_city_bulk(city, pages_per_window)

        if df.empty:
            print(f"  [{label}] 데이터 없음")
            continue

        print(f"  [{label}] {len(df):,}건 수집 완료")

        # 도시 완료 즉시 파일로 저장 (중간 종료 시 데이터 보존)
        city_file = ensure_dir(DATA_RAW_DIR) / f"bid_raw_{city}.csv"
        df.to_csv(city_file, index=False, encoding="utf-8-sig")
        print(f"  [{label}] 저장 완료: {city_file}")

        all_frames.append(df)

    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)

    if "bidNtceNo" in combined.columns and "bidNtceOrd" in combined.columns:
        combined = combined.drop_duplicates(subset=["bidNtceNo", "bidNtceOrd"], keep="first")

    return combined


def _write_national_summary(matrix: pd.DataFrame, top_items: pd.DataFrame) -> Path:
    """전국 분석 결과를 Markdown 리포트로 저장합니다."""
    target = ensure_dir(OUTPUT_TABLE_DIR) / "national_summary.md"

    city_counts = {}
    if "city" in matrix.columns:
        city_counts = matrix.groupby("city")["bid_count"].sum().to_dict()

    lines = [
        "# 전국 공공조달 수요 분석 리포트",
        "",
        "## 수집 범위",
        f"- 분석 지역 수: {matrix['district'].nunique() if not matrix.empty else 0}개",
        f"- 분석 품목군: {matrix['item_category'].nunique() if not matrix.empty else 0}개",
        "",
        "## 시/도별 공고 건수",
        "",
    ]

    for city, count in sorted(city_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {city}: {int(count):,}건")

    lines += [
        "",
        "## 지역별 추천 품목 TOP3",
        "",
    ]

    if not top_items.empty:
        for _, group in top_items.groupby("district"):
            district = group.iloc[0]["district"]
            city = group.iloc[0].get("city", "")
            label = f"{city} {district}" if city else district
            lines.append(f"### {label}")
            for row in group.sort_values("rank").itertuples(index=False):
                lines.append(
                    f"- {int(row.rank)}위: {row.item_category} "
                    f"(공고 {int(row.bid_count)}건, 점수 {row.opportunity_score:.1f})"
                )
            lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main(cities: list[str] | None = None) -> None:
    """전국(또는 지정 시/도) 수집부터 매트릭스·리포트 저장까지 한 번에 실행합니다."""
    scope = "전국" if not cities else " / ".join(CITY_LABELS.get(c, c) for c in cities)
    print(f"=== 수집 범위: {scope} ===")

    df = collect_by_cities(cities)

    if df.empty:
        print("수집된 데이터가 없습니다. API 키와 네트워크 상태를 확인하세요.")
        return

    suffix = "_".join(CITY_LABELS.get(c, c) for c in cities) if cities else "national"
    raw_path = save_csv(df, f"{DATA_RAW_DIR}/bid_raw_{suffix}.csv")
    print(f"\n원천 데이터 저장: {raw_path} ({len(df):,}건)")

    cleaned = clean_bid_data(df)
    cleaned_path = save_csv(cleaned, f"{DATA_PROCESSED_DIR}/bid_cleaned_{suffix}.csv")
    print(f"정제 데이터 저장: {cleaned_path}")

    if "city" in cleaned.columns:
        print("\n=== 시/도별 공고 수 ===")
        print(cleaned["city"].value_counts().to_string())
    print("\n=== 지역별 공고 수 (상위 20) ===")
    print(cleaned["district"].value_counts().head(20).to_string())

    target_districts = cleaned["district"].dropna().unique().tolist()
    matrix = build_opportunity_matrix(cleaned, target_districts=target_districts)
    matrix_path = save_csv(matrix, f"{OUTPUT_TABLE_DIR}/opportunity_matrix_{suffix}.csv")
    print(f"\n매트릭스 저장: {matrix_path} ({len(matrix):,}행)")

    top_items = summarize_top_items_by_district(matrix, top_n=3)
    save_csv(top_items, f"{OUTPUT_TABLE_DIR}/top_items_by_district_{suffix}.csv")

    report_path = _write_national_summary(matrix, top_items)
    print(f"리포트 저장: {report_path}")

    # 전국 수집 완료 시 metadata.json 자동 갱신
    if suffix == "national":
        try:
            from src.collect.update_metadata import update_metadata
            print("\n=== metadata.json 갱신 ===")
            update_metadata()
        except Exception as e:
            print(f"[warn] metadata 갱신 실패: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="전국 입찰공고 수집 스크립트")
    parser.add_argument(
        "--cities",
        nargs="*",
        help="수집할 시/도 이름 (예: 부산광역시 대구광역시). 생략하면 전국 전체 수집.",
    )
    args = parser.parse_args()
    main(cities=args.cities or None)
