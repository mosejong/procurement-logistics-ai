from src.config.settings import PROCUREMENT_API_KEY
from src.api.procurement_api import get_bid_list


def main():
    print("KEY EXISTS:", bool(PROCUREMENT_API_KEY))
    print("KEY LENGTH:", len(PROCUREMENT_API_KEY))

    df = get_bid_list(page_no=1, num_of_rows=5)

    if df.empty:
        print("데이터 없음 또는 인증/응답 구조 확인 필요")
    else:
        print("조회 성공")
        print(df.columns.tolist())
        print(df.head())


if __name__ == "__main__":
    main()