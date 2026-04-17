from src.api.procurement_api import get_bid_list


def main():
    df = get_bid_list(page_no=1, num_of_rows=20)
    print(df.head())

    if not df.empty:
        df.to_csv("data/raw/bid_list_sample.csv", index=False, encoding="utf-8-sig")
        print("저장 완료: data/raw/bid_list_sample.csv")
    else:
        print("데이터가 비어 있음. API 키 / endpoint / 파라미터 확인 필요")


if __name__ == "__main__":
    main()