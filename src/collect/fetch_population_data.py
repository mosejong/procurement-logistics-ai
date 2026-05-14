"""
인구 레퍼런스 데이터 로드 및 전국 수집

역할:
    - load_population_reference(): 시군구 단위 인구 CSV를 로드합니다.
      national_district_population.csv (전국) → seoul_district_population.csv (서울) 폴백.
    - collect_national_district_population(): 행안부 API (15108071, lv=2)로
      전국 17개 시도 x 시군구 인구를 수집합니다.
    - load_sido_population(): 시도 단위 연간 인구 로드 (API 15107303).
"""

from pathlib import Path

import pandas as pd

from src.api.population_api import SIDO_STDG_CODES, get_district_population, get_sido_population
from src.utils.file_handler import ensure_dir

NATIONAL_REFERENCE_PATH = Path("data/reference/national_district_population.csv")
SEOUL_REFERENCE_PATH = Path("data/reference/seoul_district_population.csv")
SIDO_REFERENCE_PATH = Path("data/reference/sido_population_2024.csv")


def load_population_reference() -> pd.DataFrame:
    """
    시군구 단위 인구 레퍼런스 CSV를 로드합니다.
    national_district_population.csv -> seoul_district_population.csv 순서로 시도합니다.
    """
    path = NATIONAL_REFERENCE_PATH if NATIONAL_REFERENCE_PATH.exists() else SEOUL_REFERENCE_PATH

    if not path.exists():
        raise FileNotFoundError(
            "인구 파일 없음. 실행: python -m src.collect.fetch_population_data"
        )

    df = pd.read_csv(path, encoding="utf-8-sig")
    # 컬럼 정규화
    col_map = {
        "sggNm": "district",
        "total_population": "total_population",
        "totNmprCnt": "total_population",
        "households": "total_households",
        "total_households": "total_households",
        "hhCnt": "total_households",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    return df[["district", "total_population", "total_households"]].rename(
        columns={"district": "district_name"}
    )


def load_sido_population() -> pd.DataFrame:
    """17개 시도 단위 인구 CSV를 로드합니다 (없으면 API 수집)."""
    if SIDO_REFERENCE_PATH.exists():
        return pd.read_csv(SIDO_REFERENCE_PATH, encoding="utf-8-sig")
    df = get_sido_population()
    if not df.empty:
        df = df[df["city"] != "전국"]
        ensure_dir("data/reference")
        df.to_csv(SIDO_REFERENCE_PATH, index=False, encoding="utf-8-sig")
    return df


def collect_national_district_population(
    ym: str = "202501",
    verbose: bool = False,
) -> pd.DataFrame:
    """
    행안부 API (15108071, lv=2)로 전국 시군구 단위 인구를 수집합니다.
    17개 시도별로 API를 호출해 합산합니다.

    Args:
        ym: 기준 년월 YYYYMM (2022-10 이후)

    Returns:
        DataFrame [city, district, total_population, male_population,
                   female_population, households, stats_ym]
    """
    frames = []
    for city in SIDO_STDG_CODES:
        print(f"  [인구] {city} 수집 중...")
        df = get_district_population(city=city, ym=ym, verbose=verbose)
        if df.empty:
            print(f"    응답 없음")
        else:
            frames.append(df)
            print(f"    {len(df)}개 시군구")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    # 세종처럼 단일 자치단체는 sggNm이 없으므로 city명으로 district 채움
    mask = result["district"].str.strip() == ""
    result.loc[mask, "district"] = result.loc[mask, "city"]
    # 그래도 비어 있는 총계행 제거
    result = result[result["district"].str.strip() != ""]
    return result


def main() -> None:
    """전국 시군구 인구 수집 후 national_district_population.csv로 저장합니다."""
    print("전국 시군구 인구 데이터 수집 시작...")
    df = collect_national_district_population()

    if df.empty:
        print("수집 결과 없음.")
        return

    out_path = ensure_dir("data/reference") / "national_district_population.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out_path} ({len(df)}개 시군구)")
    print(df.groupby("city")["district"].count().to_string())


if __name__ == "__main__":
    main()
