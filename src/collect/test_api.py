from src.api.procurement_api import get_bid_list
from src.config.settings import PROCUREMENT_API_KEY


def main() -> None:
    print("KEY EXISTS:", bool(PROCUREMENT_API_KEY))
    print("KEY LENGTH:", len(PROCUREMENT_API_KEY))

    df = get_bid_list(page_no=1, num_of_rows=5, verbose=True)

    if df.empty:
        print("데이터가 없습니다. 인증키, endpoint, 응답 구조를 확인하세요.")
    else:
        print("조회 성공")
        print(df.columns.tolist())
        print(df.head())


if __name__ == "__main__":
    main()
