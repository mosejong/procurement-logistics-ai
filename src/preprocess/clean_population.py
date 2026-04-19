import pandas as pd


DISTRICT_COLUMN_CANDIDATES = [
    "sggNm", "sigunguNm", "시군구명", "sgg_nm", "signguNm", "district_name",
]
POPULATION_COLUMN_CANDIDATES = [
    "totPopltn", "totPop", "totPpltn", "총인구수", "population", "total_population",
]
HOUSEHOLD_COLUMN_CANDIDATES = [
    "hhCnt", "hhldCnt", "householdCnt", "세대수", "households", "total_households",
]


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column
    return None


def _to_number(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce").fillna(0).astype("int64")


def clean_population_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    주민등록 인구 및 세대현황 원천 데이터를 서울 자치구 단위로 정리합니다.

    최종 표준 컬럼:
    - district_name
    - total_population
    - total_households
    """
    if df.empty:
        return pd.DataFrame(columns=["district_name", "total_population", "total_households"])

    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]

    district_col = _first_existing_column(df, DISTRICT_COLUMN_CANDIDATES)
    population_col = _first_existing_column(df, POPULATION_COLUMN_CANDIDATES)
    household_col = _first_existing_column(df, HOUSEHOLD_COLUMN_CANDIDATES)

    if district_col is None:
        raise ValueError(f"자치구 컬럼을 찾지 못했습니다. 원천 컬럼: {df.columns.tolist()}")
    if population_col is None:
        raise ValueError(f"총인구수 컬럼을 찾지 못했습니다. 원천 컬럼: {df.columns.tolist()}")
    if household_col is None:
        raise ValueError(f"세대수 컬럼을 찾지 못했습니다. 원천 컬럼: {df.columns.tolist()}")

    cleaned = pd.DataFrame(
        {
            "district_name": df[district_col].astype(str).str.strip(),
            "total_population": _to_number(df[population_col]),
            "total_households": _to_number(df[household_col]),
        }
    )
    cleaned = cleaned[cleaned["district_name"].str.endswith("구", na=False)]

    return (
        cleaned.groupby("district_name", as_index=False)
        .agg(total_population=("total_population", "sum"), total_households=("total_households", "sum"))
        .sort_values("district_name")
        .reset_index(drop=True)
    )
