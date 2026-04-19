from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.config.settings import OUTPUT_FIGURE_DIR
from src.utils.file_handler import ensure_dir


def _set_korean_font() -> None:
    """Windows에서 그래프 한글이 깨지지 않도록 맑은 고딕을 사용합니다."""
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False


def plot_opportunity_heatmap(matrix_df: pd.DataFrame, output_path: str | None = None) -> Path | None:
    """자치구 x 품목군 opportunity_score를 히트맵 이미지로 저장합니다."""
    if matrix_df.empty or "opportunity_score" not in matrix_df.columns:
        return None

    _set_korean_font()
    output_dir = ensure_dir(OUTPUT_FIGURE_DIR)
    target = Path(output_path) if output_path else output_dir / "seoul_opportunity_heatmap.png"
    pivot = matrix_df.pivot_table(
        index="district",
        columns="item_category",
        values="opportunity_score",
        aggfunc="max",
        fill_value=0,
    )

    plt.figure(figsize=(12, 7))
    image = plt.imshow(pivot.values, aspect="auto", cmap="YlGnBu")
    plt.colorbar(image, label="Opportunity score")
    plt.xticks(range(len(pivot.columns)), pivot.columns, rotation=35, ha="right")
    plt.yticks(range(len(pivot.index)), pivot.index)
    plt.title("서울 주요 자치구 x 품목군 사업기회 샘플")
    plt.tight_layout()
    plt.savefig(target, dpi=150)
    plt.close()

    return target
