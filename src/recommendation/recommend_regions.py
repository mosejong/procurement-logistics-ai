import pandas as pd


def recommend_regions_for_item(matrix: pd.DataFrame, item_category: str, top_n: int = 5) -> pd.DataFrame:
    """품목군을 넣으면 그 품목군이 눈에 띄는 지역을 반환합니다."""
    result = matrix[matrix["item_category"] == item_category].copy()
    return result.sort_values("opportunity_score", ascending=False).head(top_n)
