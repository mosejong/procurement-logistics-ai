from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.config.settings import OUTPUT_FIGURE_DIR
from src.utils.file_handler import ensure_dir


def plot_top_opportunities(matrix_df: pd.DataFrame, output_path: str | None = None) -> Path | None:
    """
    지도 시각화 전 단계의 막대그래프입니다.

    실제 지도는 행정구역 경계 데이터가 필요하므로, MVP에서는 상위 지역·품목 조합을 막대그래프로 확인합니다.
    """
    if matrix_df.empty or "opportunity_score" not in matrix_df.columns:
        return None

    top = matrix_df.sort_values("opportunity_score", ascending=True).tail(10).copy()
    top["label"] = top["district"].astype(str) + " / " + top["item_category"].astype(str)

    output_dir = ensure_dir(OUTPUT_FIGURE_DIR)
    target = Path(output_path) if output_path else output_dir / "top_opportunity_pairs.png"

    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    plt.figure(figsize=(10, 6))
    plt.barh(top["label"], top["opportunity_score"])
    plt.xlabel("Opportunity score")
    plt.title("상위 지역-품목 사업기회 샘플")
    plt.tight_layout()
    plt.savefig(target, dpi=150)
    plt.close()

    return target
