from pathlib import Path

import pandas as pd

from src.config.settings import DATA_PROCESSED_DIR
from src.utils.file_handler import save_csv

REFERENCE_PATH = Path("data/reference/seoul_district_population.csv")


def load_population_reference() -> pd.DataFrame:
    """
    행안부 주민등록인구통계 레퍼런스 데이터를 로드합니다.

    인구 데이터는 연 단위로 변동하므로 레퍼런스 CSV를 기준으로 사용합니다.
    API 연결이 확보되면 get_population_households() 결과로 교체할 수 있습니다.
    """
    if not REFERENCE_PATH.exists():
        raise FileNotFoundError(f"레퍼런스 파일이 없습니다: {REFERENCE_PATH}")

    df = pd.read_csv(REFERENCE_PATH, encoding="utf-8-sig")
    return df[["district", "total_population", "total_households"]].rename(
        columns={"district": "district_name"}
    )


def main() -> None:
    population = load_population_reference()
    cleaned_path = save_csv(population, f"{DATA_PROCESSED_DIR}/seoul_population_cleaned.csv")
    print(f"인구 데이터 저장: {cleaned_path}")
    print(f"자치구 수: {len(population)}")
    print(population.to_string(index=False))


if __name__ == "__main__":
    main()
