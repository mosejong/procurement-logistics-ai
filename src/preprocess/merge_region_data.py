import pandas as pd


def merge_region_features(bid_df: pd.DataFrame, region_df: pd.DataFrame) -> pd.DataFrame:
    if bid_df.empty or region_df.empty or "region" not in bid_df.columns:
        return bid_df.copy()

    if "region" not in region_df.columns:
        return bid_df.copy()

    return bid_df.merge(region_df, on="region", how="left")
