"""
행안부 주민등록인구현황 CSV → national_district_population.csv 변환

입력: 202305_202604_주민등록인구및세대현황_월간.csv (euc-kr, wide format)
출력: data/reference/national_district_population.csv
      [city, district, total_population, male_population, female_population, households, stats_ym]

실행:
    python -m src.collect.build_population_from_csv
    python -m src.collect.build_population_from_csv --csv 다른파일.csv
"""

import argparse
import re
from pathlib import Path

import pandas as pd

from src.config.regions import REGIONS, normalize_city_name

DEFAULT_CSV = Path("data/raw/202305_202604_주민등록인구및세대현황_월간.csv")
OUT_PATH = Path("data/reference/national_district_population.csv")

# 최신 연월 (컬럼명 접두어)
LATEST_YM = "2026년04월"
STATS_YM = "202604"


def _to_int(val) -> int:
    if pd.isna(val):
        return 0
    return int(str(val).replace(",", "").strip() or 0)


def _parse_region_name(raw: str) -> tuple[str, str | None]:
    """
    "서울특별시 종로구 (1111000000)" → ("서울특별시", "종로구")
    "서울특별시  (1100000000)"       → ("서울특별시", None)
    """
    name = raw.split("(")[0].strip()
    parts = name.split()
    if len(parts) == 1:
        return parts[0], None
    city = parts[0]
    district = parts[-1]
    return city, district


def _city_name_alias(raw_city: str) -> str:
    """CSV의 시도명 → REGIONS 키로 정규화. regions.normalize_city_name 위임."""
    return normalize_city_name(raw_city)


def build_population(csv_path: Path) -> pd.DataFrame:
    df_raw = pd.read_csv(csv_path, encoding="euc-kr")

    col_total = f"{LATEST_YM}_총인구수"
    col_male  = f"{LATEST_YM}_남자 인구수"
    col_female = f"{LATEST_YM}_여자 인구수"
    col_house  = f"{LATEST_YM}_세대수"

    missing = [c for c in [col_total, col_male, col_female, col_house] if c not in df_raw.columns]
    if missing:
        # 컬럼명이 조금 다를 수 있어 패턴 매칭으로 재시도
        ym_short = LATEST_YM.replace("년", "년").replace("월", "월")
        total_cols = [c for c in df_raw.columns if "총인구수" in c]
        male_cols  = [c for c in df_raw.columns if "남자" in c and "인구수" in c]
        fem_cols   = [c for c in df_raw.columns if "여자" in c and "인구수" in c]
        house_cols = [c for c in df_raw.columns if "세대수" in c]
        if not total_cols:
            raise ValueError(f"총인구수 컬럼을 찾을 수 없습니다. 확인 필요: {csv_path}")
        col_total  = total_cols[-1]   # 가장 최근 = 마지막
        col_male   = male_cols[-1]  if male_cols  else None
        col_female = fem_cols[-1]   if fem_cols   else None
        col_house  = house_cols[-1] if house_cols else None

    print(f"사용 컬럼: {col_total}")

    records = []
    for _, row in df_raw.iterrows():
        raw_name = str(row.iloc[0])
        city_raw, district = _parse_region_name(raw_name)
        city = _city_name_alias(city_raw)

        if district is None:
            continue  # 시도 합계 행 제외

        # REGIONS에 없는 시도면 제외
        if city not in REGIONS:
            continue

        # REGIONS에 없는 district는 제외 (구 행정구역명 등)
        valid_districts = set(REGIONS[city])
        if district not in valid_districts:
            continue

        total  = _to_int(row[col_total])
        if total == 0:
            continue  # 명칭 변경 전 구 행정구역명 행(최신 연월 데이터 없음) 제외

        male   = _to_int(row[col_male])   if col_male   else 0
        female = _to_int(row[col_female]) if col_female else 0
        house  = _to_int(row[col_house])  if col_house  else 0

        records.append({
            "city":             city,
            "district":         district,
            "total_population": total,
            "male_population":  male,
            "female_population": female,
            "households":       house,
            "stats_ym":         STATS_YM,
        })

    result = pd.DataFrame(records)
    if result.empty:
        return result

    # 세종시 특수 처리: CSV에서 "세종특별자치시" 통계가 district 없이 나올 수 있음
    if "세종특별자치시" in REGIONS:
        세종_row = df_raw[df_raw.iloc[:, 0].str.contains("세종특별자치시", na=False)]
        for _, row in 세종_row.iterrows():
            name = str(row.iloc[0]).split("(")[0].strip()
            if name.strip() == "세종특별자치시":
                records.append({
                    "city":             "세종특별자치시",
                    "district":         "세종시",
                    "total_population": _to_int(row[col_total]),
                    "male_population":  _to_int(row[col_male])   if col_male   else 0,
                    "female_population": _to_int(row[col_female]) if col_female else 0,
                    "households":       _to_int(row[col_house])  if col_house  else 0,
                    "stats_ym":         STATS_YM,
                })

    result = pd.DataFrame(records).drop_duplicates(subset=["city", "district"])
    return result.sort_values(["city", "district"]).reset_index(drop=True)


def main(csv_path: Path | None = None) -> None:
    csv_path = csv_path or DEFAULT_CSV
    if not csv_path.exists():
        print(f"CSV 없음: {csv_path}")
        return

    print(f"읽기: {csv_path}")
    result = build_population(csv_path)

    if result.empty:
        print("결과 없음 — 컬럼명 또는 지역명 형식을 확인하세요.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"저장: {OUT_PATH}")
    print(f"  {len(result)}개 지역, 시/도 커버리지:")
    print(result.groupby("city")["district"].count().to_string())

    # 누락된 REGIONS 지역 리포트
    all_pairs = {(city, d) for city, ds in REGIONS.items() for d in ds}
    result_pairs = {(r["city"], r["district"]) for r in result.to_dict("records")}
    missing = sorted(all_pairs - result_pairs)
    if missing:
        print(f"\n[누락] {len(missing)}개 지역 (CSV에 없음 - 행정구역명 불일치 가능):")
        for c, d in missing[:20]:
            print(f"  {c} {d}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=None, help="CSV 파일 경로")
    args = parser.parse_args()
    main(args.csv)
