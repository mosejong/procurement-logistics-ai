from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.api.procurement_api import get_bid_list
from src.collect.fetch_population_data import load_population_reference
from src.config.settings import DATA_PROCESSED_DIR, DATA_RAW_DIR, OUTPUT_REPORT_DIR, OUTPUT_TABLE_DIR
from src.features.build_features import build_feature_table
from src.features.build_opportunity_matrix import TARGET_DISTRICTS, build_opportunity_matrix, summarize_top_items_by_district
from src.preprocess.clean_bid_data import clean_bid_data
from src.utils.file_handler import ensure_dir, save_csv
from src.visualization.plot_heatmap import plot_opportunity_heatmap


def _date_windows(days_back: int = 730, window_days: int = 30) -> list[tuple[str, str]]:
    """API 조회 범위 초과를 피하려고 전체 기간을 30일 단위로 쪼갭니다."""
    end = datetime.now()
    start = end - timedelta(days=days_back)
    windows = []

    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=window_days), end)
        windows.append(
            (
                cursor.strftime("%Y%m%d0000"),
                window_end.strftime("%Y%m%d2359"),
            )
        )
        cursor = window_end + timedelta(days=1)

    return windows


def _collect_bids_for_district(district: str, pages_per_window: int = 5) -> pd.DataFrame:
    """
    특정 자치구 수요기관의 공고를 기간별로 수집합니다.

    dminsttNm 파라미터로 API 레벨에서 자치구 기관만 필터링하므로,
    전국 공고를 긁어 텍스트 추출하는 방식보다 구별 데이터 비율이 훨씬 높습니다.
    수집된 행에는 _source_district 컬럼을 붙여 전처리 단계에서 신뢰할 수 있는 지역 정보로 씁니다.
    """
    frames = []
    for start_date, end_date in _date_windows():
        window_count = 0
        for page_no in range(1, pages_per_window + 1):
            df = get_bid_list(
                page_no=page_no,
                num_of_rows=100,
                start_date=start_date,
                end_date=end_date,
                extra_params={"dminsttNm": district},
                verbose=False,
            )
            if df.empty:
                break
            frames.append(df)
            window_count += len(df)

        if window_count:
            print(f"  {start_date[:8]}~{end_date[:8]}: {window_count}건")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True).drop_duplicates()
    result["_source_district"] = district
    return result


def _collect_all_districts(target_districts: list[str]) -> pd.DataFrame:
    """대상 자치구 전체를 순서대로 수집해서 하나의 DataFrame으로 합칩니다."""
    all_frames = []
    for district in target_districts:
        print(f"\n[수집 시작] {district}")
        df = _collect_bids_for_district(district)
        if df.empty:
            print(f"  → 데이터 없음")
            continue
        print(f"  → {len(df)}건 수집 완료")
        all_frames.append(df)

    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)

    # 같은 공고가 여러 구 수집에서 중복될 수 있으나, _source_district를 기준으로 첫 번째를 유지합니다.
    if "bidNtceNo" in combined.columns and "bidNtceOrd" in combined.columns:
        combined = combined.drop_duplicates(subset=["bidNtceNo", "bidNtceOrd"], keep="first")

    return combined


def _write_summary_report(matrix: pd.DataFrame, top_items: pd.DataFrame) -> Path:
    """분석 결과를 사람이 읽기 쉬운 Markdown 리포트로 저장합니다."""
    target = ensure_dir(OUTPUT_REPORT_DIR) / "seoul_sample_summary.md"
    covered = sorted(matrix["district"].unique().tolist()) if not matrix.empty else []
    missing = [d for d in TARGET_DISTRICTS if d not in covered]

    lines = [
        "# 서울 주요 자치구 사업기회 샘플 리포트",
        "",
        "## 해석 기준",
        "",
        "- 이 결과는 조달청 입찰공고 데이터를 공공수요 신호로 해석한 샘플입니다.",
        "- 창업 성공을 예측하는 값이 아니라, 창업상담 과정에서 참고할 수 있는 근거 자료입니다.",
        "- 점수는 공고 수, 금액 규모, 최근성을 결합한 초기 지표입니다.",
        "",
        "## 데이터 커버리지",
        "",
        f"- 샘플에 잡힌 관심 자치구: {', '.join(covered) if covered else '없음'}",
        f"- 이번 샘플에서 부족한 관심 자치구: {', '.join(missing) if missing else '없음'}",
        "",
        "## 자치구별 추천 품목 TOP",
        "",
    ]

    if top_items.empty:
        lines.append("이번 샘플에서는 추천 품목을 산출할 수 있는 관심 자치구 데이터가 부족했습니다.")
    else:
        for district, group in top_items.groupby("district"):
            lines.append(f"### {district}")
            for row in group.sort_values("rank").itertuples(index=False):
                lines.append(
                    f"- {int(row.rank)}위: {row.item_category} "
                    f"(공고 {int(row.bid_count)}건, 금액 {int(row.amount_sum):,}원, 점수 {row.opportunity_score})"
                )
            lines.append("")

    lines.extend(
        [
            "## 다음 보완 포인트",
            "",
            "- 주민등록 인구 및 세대현황을 붙여 인구 대비 공공수요를 계산합니다.",
            "- 품목군 키워드 사전을 계속 보완해 `기타` 비중을 줄입니다.",
            "- 낙찰정보 API를 붙여 품목별 평균 낙찰 소요일을 계산합니다.",
        ]
    )
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main() -> None:
    """서울 샘플 수집부터 표/그래프/리포트 저장까지 한 번에 실행합니다."""
    df = _collect_all_districts(TARGET_DISTRICTS)

    if df.empty:
        print("데이터가 비어 있습니다. API 키, 조회 기간, 응답 구조를 확인하세요.")
        return

    raw_path = save_csv(df, f"{DATA_RAW_DIR}/seoul_bid_sample.csv")

    cleaned = clean_bid_data(df)
    cleaned_path = save_csv(cleaned, f"{DATA_PROCESSED_DIR}/seoul_bid_cleaned.csv")

    # 자치구별 수집 후 district 분포를 확인합니다.
    district_counts = cleaned["district"].value_counts()
    print("\n=== 자치구별 공고 수 ===")
    print(district_counts.to_string())

    matrix = build_opportunity_matrix(cleaned)
    matrix_path = save_csv(matrix, f"{OUTPUT_TABLE_DIR}/seoul_opportunity_matrix.csv")

    top_items = summarize_top_items_by_district(matrix, top_n=3)
    top_items_path = save_csv(top_items, f"{OUTPUT_TABLE_DIR}/seoul_top_items_by_district.csv")
    report_path = _write_summary_report(matrix, top_items)

    # 인구 보정 피처 테이블: 인구 대비 공공수요 밀도 지표를 추가합니다.
    population = load_population_reference()
    feature_table = build_feature_table(matrix, population)
    feature_path = save_csv(feature_table, f"{OUTPUT_TABLE_DIR}/seoul_feature_table.csv")

    figure_path = plot_opportunity_heatmap(matrix)

    print(f"\n원천 데이터 저장: {raw_path}")
    print(f"정제 데이터 저장: {cleaned_path}")
    print(f"지역-품목 매트릭스 저장: {matrix_path}")
    print(f"자치구별 추천 품목 TOP3 저장: {top_items_path}")
    print(f"요약 리포트 저장: {report_path}")
    print(f"인구 보정 피처 테이블 저장: {feature_path}")
    if figure_path:
        print(f"히트맵 저장: {figure_path}")

    if not top_items.empty:
        print("\n=== 서울 주요 자치구 추천 품목 샘플 ===")
        print(top_items[["district", "district_profile", "rank", "item_category", "bid_count", "amount_sum", "opportunity_score"]])


if __name__ == "__main__":
    main()
