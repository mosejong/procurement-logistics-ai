from datetime import datetime

from src.api.population_api import get_population_households
from src.config.settings import DATA_PROCESSED_DIR, DATA_RAW_DIR
from src.preprocess.clean_population import clean_population_data
from src.utils.file_handler import save_csv


def default_stat_month() -> str:
    """전월 기준 YYYYMM을 기본 조회월로 사용합니다."""
    today = datetime.now()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}{month:02d}"


def main() -> None:
    stat_month = default_stat_month()
    raw = get_population_households(stat_month=stat_month, verbose=True)

    if raw.empty:
        print("인구/세대현황 데이터가 비어 있습니다. API 키, endpoint, 조회월을 확인하세요.")
        return

    raw_path = save_csv(raw, f"{DATA_RAW_DIR}/seoul_population_raw.csv")
    cleaned = clean_population_data(raw)
    cleaned_path = save_csv(cleaned, f"{DATA_PROCESSED_DIR}/seoul_population_cleaned.csv")

    print(f"인구 원천 데이터 저장: {raw_path}")
    print(f"인구 정제 데이터 저장: {cleaned_path}")
    print(cleaned.head())


if __name__ == "__main__":
    main()
