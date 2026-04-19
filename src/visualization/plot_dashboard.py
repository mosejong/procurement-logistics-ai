"""
Deprecated compatibility wrapper.

새 프로젝트 구조에서는 아래 파일을 직접 사용합니다.

- `src.visualization.plot_heatmap`
- `src.visualization.plot_opportunity_map`
"""

from src.visualization.plot_heatmap import plot_opportunity_heatmap  # noqa: F401
from src.visualization.plot_opportunity_map import plot_top_opportunities  # noqa: F401
