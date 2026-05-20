"""
aT 학교급식 계약정보 수집 + 지역별 요약

역할:
    aT 학교급식 계약정보를 시도별로 수집해 지역별 요약 테이블을 만듭니다.
    입찰공고의 급식/식자재 수요와 함께 "공고=의사 / 계약=실측" 2단 구조를 구성합니다.

출력: outputs/tables/school_meal_contract_summary.csv
컬럼: region, contract_count, contract_amount_sum, buyer_count,
       supplier_count, top_supplier_region, latest_contract_date

실행:
    python -m src.collect.collect_school_meal
    python -m src.collect.collect_school_meal --sido 부산 서울

샘플 CSV 모드:
    BASE_URL_SCHOOL_MEAL이 .env에 없으면 샘플 데이터로 동작합니다.
    실제 API를 쓰려면 data.go.kr에서 "aT 학교급식 계약정보" 서비스 URL을 확인해
    .env에 BASE_URL_SCHOOL_MEAL=https://... 로 추가하세요.
"""

import argparse
from pathlib import Path

import pandas as pd

from src.config.settings import BASE_URL_SCHOOL_MEAL, OUTPUT_TABLE_DIR

ROOT = Path(__file__).parent.parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"
OUT_PATH = TABLES_DIR / "school_meal_contract_summary.csv"

SIDO_LIST = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

SIDO_TO_CITY = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
    "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
    "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
    "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
    "경남": "경상남도", "제주": "제주특별자치도",
}


def _sample_data() -> pd.DataFrame:
    """API 미연결 시 구조 확인용 샘플 데이터."""
    rows = [
        {"purchsInsttSido": "서울", "ctrtAmt": 50000000, "purchsInsttNm": "○○초등학교", "shtNm": "A식자재", "shtSido": "경기", "ctrtDate": "2024-03-01"},
        {"purchsInsttSido": "부산", "ctrtAmt": 30000000, "purchsInsttNm": "△△중학교", "shtNm": "B농산물", "shtSido": "전남", "ctrtDate": "2024-04-15"},
        {"purchsInsttSido": "부산", "ctrtAmt": 25000000, "purchsInsttNm": "□□고등학교", "shtNm": "C유통", "shtSido": "부산", "ctrtDate": "2024-05-10"},
        {"purchsInsttSido": "대구", "ctrtAmt": 20000000, "purchsInsttNm": "◇◇초등학교", "shtNm": "D식품", "shtSido": "경북", "ctrtDate": "2024-03-20"},
        {"purchsInsttSido": "대전", "ctrtAmt": 35000000, "purchsInsttNm": "★★학교", "shtNm": "E유통", "shtSido": "충남", "ctrtDate": "2024-06-01"},
    ]
    df = pd.DataFrame(rows)
    df["ctrtDate"] = pd.to_datetime(df["ctrtDate"])
    return df


def _collect_api(sido_list: list[str]) -> pd.DataFrame:
    """실제 API 호출 (BASE_URL_SCHOOL_MEAL 설정 필요)."""
    from src.api.school_meal_api import get_school_meal_contracts, clean_school_meal

    frames = []
    for sido in sido_list:
        print(f"  [{sido}] 수집 중...")
        for page in range(1, 11):
            df = get_school_meal_contracts(page_no=page, num_of_rows=100, sido=sido, verbose=False)
            if df.empty:
                break
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    raw = pd.concat(frames, ignore_index=True).drop_duplicates()
    return clean_school_meal(raw)


def _summarize(df: pd.DataFrame) -> pd.DataFrame:
    """시도별 집계."""
    if "purchsInsttSido" not in df.columns:
        return pd.DataFrame()

    grp = df.groupby("purchsInsttSido")

    summary_rows = []
    for sido, group in grp:
        top_supplier = (
            group["shtSido"].value_counts().index[0]
            if "shtSido" in group.columns and not group["shtSido"].isna().all()
            else None
        )
        summary_rows.append({
            "sido": sido,
            "city": SIDO_TO_CITY.get(sido, sido),
            "contract_count": len(group),
            "contract_amount_sum": group["ctrtAmt"].sum() if "ctrtAmt" in group.columns else 0,
            "buyer_count": group["purchsInsttNm"].nunique() if "purchsInsttNm" in group.columns else 0,
            "supplier_count": group["shtNm"].nunique() if "shtNm" in group.columns else 0,
            "top_supplier_region": top_supplier,
            "latest_contract_date": group["ctrtDate"].max().strftime("%Y-%m-%d")
                                    if "ctrtDate" in group.columns and not group["ctrtDate"].isna().all()
                                    else None,
        })

    return pd.DataFrame(summary_rows)


def run(sido_list: list[str] | None = None) -> None:
    targets = sido_list or SIDO_LIST

    use_api = bool(BASE_URL_SCHOOL_MEAL)

    if use_api:
        print("[학교급식] API 모드")
        df = _collect_api(targets)
    else:
        print("[학교급식] 샘플 모드 (BASE_URL_SCHOOL_MEAL 미설정)")
        print("  → data.go.kr에서 'aT 학교급식 계약정보' 서비스 URL을 .env에 추가하면 실데이터로 전환됩니다.")
        df = _sample_data()

    if df.empty:
        print("[경고] 데이터 없음. API 설정 확인 필요.")
        return

    summary = _summarize(df)
    if summary.empty:
        print("[경고] 집계 실패.")
        return

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] {OUT_PATH.name} ({len(summary)}행)")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="aT 학교급식 계약정보 수집")
    parser.add_argument("--sido", nargs="+", help="수집할 시도 단축명 (예: 부산 서울)")
    args = parser.parse_args()
    run(sido_list=args.sido)
