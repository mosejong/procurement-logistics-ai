from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.api.procurement_api import get_bid_list
from src.config.settings import DATA_PROCESSED_DIR, DATA_RAW_DIR, OUTPUT_REPORT_DIR, OUTPUT_TABLE_DIR
from src.features.build_opportunity_matrix import build_opportunity_matrix, summarize_top_items_by_district
from src.preprocess.clean_bid_data import clean_bid_data
from src.utils.file_handler import ensure_dir, save_csv
from src.visualization.plot_heatmap import plot_opportunity_heatmap


def _date_windows(days_back: int = 180, window_days: int = 30) -> list[tuple[str, str]]:
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


def _collect_bids_by_windows(pages_per_window: int = 5) -> pd.DataFrame:
    """쪼갠 기간별로 여러 페이지를 수집해서 하나의 DataFrame으로 합칩니다."""
    frames = []
    for start_date, end_date in _date_windows():
        window_count = 0
        for page_no in range(1, pages_per_window + 1):
            # 한 기간 안에서도 1페이지만 보면 서울 자치구 공고가 적어서 여러 페이지를 봅니다.
            df = get_bid_list(
                page_no=page_no,
                num_of_rows=100,
                start_date=start_date,
                end_date=end_date,
                verbose=False,
            )
            if df.empty:
                continue

            frames.append(df)
            window_count += len(df)

        if window_count:
            print(f"수집 성공: {start_date}~{end_date} / {window_count}건")
        else:
            print(f"수집 없음: {start_date}~{end_date}")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True).drop_duplicates()


def _write_summary_report(matrix: pd.DataFrame, top_items: pd.DataFrame) -> Path:
    """분석 결과를 사람이 읽기 쉬운 Markdown 리포트로 저장합니다."""
    target = ensure_dir(OUTPUT_REPORT_DIR) / "seoul_sample_summary.md"
    covered = sorted(matrix["district"].unique().tolist()) if not matrix.empty else []
    target_districts = ["관악구", "강남구", "마포구", "영등포구", "성동구", "종로구", "송파구"]
    missing = [district for district in target_districts if district not in covered]

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
            "- 관심 자치구별 공고 수가 적은 경우 조회 기간과 페이지 수를 늘립니다.",
            "- 주민등록 인구 및 세대현황을 붙여 인구 대비 공공수요를 계산합니다.",
            "- 성·연령별 인구 데이터는 2차 고도화 단계에서 추가합니다.",
            "- 품목군 키워드 사전을 계속 보완해 `기타` 비중을 줄입니다.",
        ]
    )
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main() -> None:
    """서울 샘플 수집부터 표/그래프/리포트 저장까지 한 번에 실행합니다."""
    df = _collect_bids_by_windows()

    if df.empty:
        print("데이터가 비어 있습니다. API 키, 조회 기간, 응답 구조를 확인하세요.")
        return

    raw_path = save_csv(df, f"{DATA_RAW_DIR}/seoul_bid_sample.csv")

    # 원천 공고를 표준 컬럼으로 바꾸고, 서울 자치구와 품목군을 붙입니다.
    cleaned = clean_bid_data(df)
    cleaned_path = save_csv(cleaned, f"{DATA_PROCESSED_DIR}/seoul_bid_cleaned.csv")

    # 프로젝트의 핵심 결과표: 자치구 x 품목군 x 점수
    matrix = build_opportunity_matrix(cleaned)
    matrix_path = save_csv(matrix, f"{OUTPUT_TABLE_DIR}/seoul_opportunity_matrix.csv")

    # 발표/점검용으로 자치구별 TOP3 품목만 따로 저장합니다.
    top_items = summarize_top_items_by_district(matrix, top_n=3)
    top_items_path = save_csv(top_items, f"{OUTPUT_TABLE_DIR}/seoul_top_items_by_district.csv")
    report_path = _write_summary_report(matrix, top_items)

    # Streamlit 화면과 보고서에서 볼 히트맵 이미지입니다.
    figure_path = plot_opportunity_heatmap(matrix)

    print(f"원천 데이터 저장: {raw_path}")
    print(f"정제 데이터 저장: {cleaned_path}")
    print(f"지역-품목 매트릭스 저장: {matrix_path}")
    print(f"자치구별 추천 품목 TOP3 저장: {top_items_path}")
    print(f"요약 리포트 저장: {report_path}")
    if figure_path:
        print(f"히트맵 저장: {figure_path}")

    if not top_items.empty:
        print("\n=== 서울 주요 자치구 추천 품목 샘플 ===")
        print(top_items[["district", "district_profile", "rank", "item_category", "bid_count", "amount_sum", "opportunity_score"]])


if __name__ == "__main__":
    main()
