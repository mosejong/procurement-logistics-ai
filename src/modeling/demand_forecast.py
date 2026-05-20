"""
카테고리별 월별 수요 트렌드 예측

나라장터 입찰공고 2년치 데이터로 월별 발주 건수 트렌드를 분석하고
향후 3개월 예상 건수를 선형 추세로 예측합니다.

한계:
    24개월 데이터로 seasonality 포착은 어려움.
    트렌드 방향(증가/감소/유지) 파악 용도로만 사용.

출력:
    outputs/tables/demand_forecast.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

BID_PATH = Path("data/processed/bid_cleaned_national.csv")
OUT_PATH = Path("outputs/tables/demand_forecast.csv")


def load_monthly(item_category: str | None = None) -> pd.DataFrame:
    """입찰공고를 월별 × 카테고리별로 집계합니다."""
    df = pd.read_csv(BID_PATH, low_memory=False, usecols=["posted_date", "item_category", "estimated_amount"])
    df["posted_date"] = pd.to_datetime(df["posted_date"], errors="coerce")
    df = df.dropna(subset=["posted_date"])
    df["ym"] = df["posted_date"].dt.to_period("M")

    if item_category:
        df = df[df["item_category"] == item_category]

    monthly = (
        df.groupby(["ym", "item_category"])
        .agg(bid_count=("posted_date", "count"), amount_sum=("estimated_amount", "sum"))
        .reset_index()
    )
    monthly["ym_str"] = monthly["ym"].astype(str)
    return monthly


def forecast_category(monthly: pd.DataFrame, category: str, months_ahead: int = 6) -> pd.DataFrame:
    """
    단일 카테고리 월별 건수에 선형 추세를 피팅하고 미래 예측합니다.
    """
    cat = monthly[monthly["item_category"] == category].sort_values("ym").copy()
    if len(cat) < 6:
        return pd.DataFrame()

    cat = cat.reset_index(drop=True)
    cat["t"] = range(len(cat))

    X = cat[["t"]].values
    y = cat["bid_count"].values

    model = LinearRegression()
    model.fit(X, y)

    # 과거 피팅값
    cat["fitted"] = model.predict(X).round(1)
    cat["residual"] = cat["bid_count"] - cat["fitted"]

    # 미래 예측
    last_t = cat["t"].max()
    last_ym = cat["ym"].max()
    future_rows = []
    for i in range(1, months_ahead + 1):
        t_fut = last_t + i
        ym_fut = last_ym + i
        pred = max(0, round(model.predict([[t_fut]])[0], 1))
        future_rows.append({
            "ym": ym_fut,
            "ym_str": str(ym_fut),
            "item_category": category,
            "bid_count": None,
            "amount_sum": None,
            "t": t_fut,
            "fitted": pred,
            "residual": None,
            "is_forecast": True,
        })

    cat["is_forecast"] = False
    result = pd.concat([cat, pd.DataFrame(future_rows)], ignore_index=True)

    # 트렌드 방향: 최근 6개월 기울기 기준 (전체 평균보다 모멘텀 민감)
    slope = model.coef_[0]
    n_recent = min(6, len(cat))
    recent_cat = cat.tail(n_recent).reset_index(drop=True)
    recent_slope = float(np.polyfit(range(n_recent), recent_cat["bid_count"].values, 1)[0])
    # 최근 기울기가 전체보다 크면 최근 값 우선 사용
    display_slope = recent_slope if abs(recent_slope) >= abs(slope) else slope
    result["trend"] = "증가" if display_slope > 1.0 else ("감소" if display_slope < -1.0 else "유지")
    result["slope_per_month"] = round(display_slope, 2)

    # 계절성 감지: CV > 0.8 (강한 계절성만 경고 — 0.5는 너무 민감)
    cv = float(cat["residual"].std() / (cat["bid_count"].mean() + 1e-9))
    result["seasonal_cv"] = round(cv, 3)
    result["has_seasonality"] = cv > 0.8

    return result


def run(categories: list[str] | None = None, months_ahead: int = 6) -> None:
    print("[demand_forecast] 월별 수요 예측 시작...")
    monthly = load_monthly()

    if categories is None:
        categories = monthly["item_category"].unique().tolist()

    frames = []
    for cat in categories:
        result = forecast_category(monthly, cat, months_ahead)
        if not result.empty:
            frames.append(result)
            trend = result["trend"].iloc[0]
            slope = result["slope_per_month"].iloc[0]
            forecast_vals = result[result["is_forecast"]]["fitted"].tolist()
            print(f"  {cat}: 트렌드={trend} (월 {slope:+.1f}건), 예측={forecast_vals}")

    if not frames:
        print("예측 결과 없음")
        return

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT_PATH} ({len(out)}행)")


if __name__ == "__main__":
    run()
