import pandas as pd


def recommend_items_for_district(matrix: pd.DataFrame, district: str, top_n: int = 5) -> pd.DataFrame:
    """지역을 넣으면 그 지역에서 눈에 띄는 품목군을 반환합니다."""
    result = matrix[matrix["district"] == district].copy()
    return result.sort_values("opportunity_score", ascending=False).head(top_n)
