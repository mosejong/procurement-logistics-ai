"""
나라장터 계약정보 수집 스크립트

용도:
    공고=의사 / 계약=실측 2단 구조 검증을 위한 실계약 데이터 수집.
    demo 및 PPT 근거 자료용 (전수 수집이 아닌 샘플 검증 목적).

사용:
    python -m src.collect.collect_contracts                   # 기본: 최근 30일, 전국
    python -m src.collect.collect_contracts --days 14         # 최근 14일
    python -m src.collect.collect_contracts --filter 부산     # 부산 필터
    python -m src.collect.collect_contracts --filter 해운대구 --days 90

API 제약:
    - 조회기간 7일 이내 (window 분할 자동 처리)
    - 서버사이드 지역 필터 미지원 → 로컬 필터링
    - 일일 호출 제한 1,000회 (개발계정)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.api.contract_api import clean_contract_data, collect_contracts_national

OUTPUT_DIR = Path("outputs/tables")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="나라장터 계약정보 수집")
    parser.add_argument("--days", type=int, default=30, help="수집 기간 (일, 기본 30)")
    parser.add_argument("--filter", type=str, default=None, help="수요기관명 키워드 필터 (예: 부산, 해운대구)")
    parser.add_argument("--type", type=str, default="물품", choices=["물품", "용역", "공사"])
    parser.add_argument("--pages", type=int, default=20, help="윈도우당 최대 페이지 수")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    filter_tag = args.filter or "전국"
    print(f"[collect_contracts] 최근 {args.days}일 {args.type} 계약 수집 (필터: {filter_tag})")

    df = collect_contracts_national(
        days_back=args.days,
        window_days=7,
        pages_per_window=args.pages,
        business_type=args.type,
        district_filter=args.filter,
        verbose=args.verbose,
    )

    if df.empty:
        print("[collect_contracts] 수집 결과 없음")
        sys.exit(0)

    df = clean_contract_data(df)

    # 출력 파일명
    tag = filter_tag.replace(" ", "_")
    out_path = OUTPUT_DIR / f"contract_sample_{tag}_{args.days}d.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    # 요약
    total_cnt = len(df)
    total_amt = df["cntrctAmt"].sum() if "cntrctAmt" in df.columns else 0
    joined = df["ntceNo"].notna().sum() if "ntceNo" in df.columns else 0

    print(f"\n{'='*50}")
    print(f"수집 건수    : {total_cnt:,}건")
    print(f"총 계약금액  : {total_amt/1e8:.1f}억원")
    print(f"공고번호 매핑: {joined}/{total_cnt}건 ({100*joined/total_cnt:.1f}%)")
    print(f"저장 경로    : {out_path}")

    # 상위 기관별 요약
    if "dminsttNm" in df.columns and total_cnt > 0:
        top = (
            df.groupby("dminsttNm")
            .agg(건수=("cntrctAmt", "count"), 금액합계=("cntrctAmt", "sum"))
            .sort_values("금액합계", ascending=False)
            .head(10)
        )
        top["금액합계(억)"] = (top["금액합계"] / 1e8).round(2)
        print("\n[수요기관별 상위 10개]")
        print(top[["건수", "금액합계(억)"]].to_string())


if __name__ == "__main__":
    main()
