import pandas as pd


def clean_bid_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 필요하면 여기서 컬럼명 확인 후 수정
    df.columns = [col.strip() for col in df.columns]

    return df