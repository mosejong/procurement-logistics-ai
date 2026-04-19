from src.api.procurement_api import get_bid_list
from src.config.settings import DATA_PROCESSED_DIR, DATA_RAW_DIR
from src.preprocess.clean_bid_data import clean_bid_data
from src.utils.file_handler import save_csv


def main() -> None:
    """
    조달청 입찰공고 원천 데이터를 가져와 raw/processed CSV로 저장합니다.

    사업기회 샘플 결과까지 만들려면 `python -m src.collect.build_seoul_sample`을 실행하세요.
    """
    df = get_bid_list(page_no=1, num_of_rows=100, verbose=True)

    if df.empty:
        print("데이터가 비어 있습니다. API 키, endpoint, 응답 구조를 확인하세요.")
        return

    raw_path = save_csv(df, f"{DATA_RAW_DIR}/bid_list_sample.csv")
    cleaned = clean_bid_data(df)
    processed_path = save_csv(cleaned, f"{DATA_PROCESSED_DIR}/bid_list_cleaned.csv")

    print(f"원천 데이터 저장: {raw_path}")
    print(f"정제 데이터 저장: {processed_path}")


if __name__ == "__main__":
    main()
