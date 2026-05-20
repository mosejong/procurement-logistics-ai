"""
수요공백(블루오션) 이상탐지

opportunity_score가 높은데 competition_score가 낮은 지역을 탐지합니다.
Isolation Forest로 "수요 대비 경쟁이 비정상적으로 낮은" 지역을 추출합니다.

출력:
    district × item_category 행렬에 anomaly_score, is_blue_ocean 컬럼 추가
    outputs/tables/blue_ocean_districts.csv
"""

from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

OPP_PATH = Path("outputs/tables/opportunity_matrix_national.csv")
OUT_PATH = Path("outputs/tables/blue_ocean_districts.csv")


def detect_blue_ocean(
    min_bid_count: int = 5,
    top_n: int = 50,
    contamination: float = 0.1,
) -> pd.DataFrame:
    """
    수요공백 지역을 탐지합니다.

    Args:
        min_bid_count: 최소 공고 건수 (노이즈 제거용)
        top_n: 반환할 블루오션 상위 N개
        contamination: Isolation Forest 이상치 비율

    Returns:
        블루오션 지역 DataFrame (anomaly_score 내림차순)
    """
    df = pd.read_csv(OPP_PATH)
    df = df[df["bid_count"] >= min_bid_count].copy()

    # 수요공백 특성: opportunity_score 높고 competition_score 낮음
    # competition_score를 반전해 "경쟁 낮음 = 높은 점수"로 변환
    features = df[["opportunity_score", "competition_score"]].copy()
    features["competition_gap"] = 1.0 - features["competition_score"]

    X = features[["opportunity_score", "competition_gap"]].values
    X_scaled = MinMaxScaler().fit_transform(X)

    iso = IsolationForest(contamination=contamination, random_state=42)
    df["anomaly_label"] = iso.fit_predict(X_scaled)       # -1: 이상치(블루오션 후보)
    df["anomaly_score"] = -iso.score_samples(X_scaled)    # 높을수록 이상도 높음

    # 블루오션 = 이상치 중 opportunity_score 상위
    blue = df[df["anomaly_label"] == -1].copy()
    blue = blue.sort_values("anomaly_score", ascending=False).head(top_n)
    blue["is_blue_ocean"] = True

    return blue[[
        "city", "district", "item_category",
        "bid_count", "opportunity_score", "competition_score",
        "anomaly_score", "is_blue_ocean",
    ]].reset_index(drop=True)


def run(top_n: int = 50) -> None:
    print("[demand_anomaly] 수요공백 이상탐지 시작...")
    result = detect_blue_ocean(top_n=top_n)
    result.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    print(f"블루오션 지역 {len(result)}개 탐지")
    print(f"저장: {OUT_PATH}")
    print()
    print("[상위 10개 블루오션 지역]")
    print(result[["city", "district", "item_category", "bid_count", "opportunity_score", "competition_score"]].head(10).to_string(index=False))


if __name__ == "__main__":
    run()
