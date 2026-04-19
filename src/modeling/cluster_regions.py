import pandas as pd


def cluster_regions(feature_df: pd.DataFrame, n_clusters: int = 4) -> pd.DataFrame:
    """
    지역 특성 기반 클러스터링을 위한 자리입니다.

    현재는 안전한 MVP 구조 정리가 목적이라 실제 모델은 아직 적용하지 않습니다.
    이후 인구/세대/연령/상권 feature가 붙으면 KMeans 같은 모델을 여기에 넣습니다.
    """
    clustered = feature_df.copy()
    clustered["cluster"] = pd.NA
    clustered["cluster_note"] = f"TODO: add clustering model with n_clusters={n_clusters}"
    return clustered
