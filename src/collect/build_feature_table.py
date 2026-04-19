import pandas as pd

from src.config.settings import DATA_PROCESSED_DIR, OUTPUT_TABLE_DIR
from src.features.build_features import build_feature_table
from src.utils.file_handler import save_csv


def main() -> None:
    matrix_path = f"{OUTPUT_TABLE_DIR}/seoul_opportunity_matrix.csv"
    population_path = f"{DATA_PROCESSED_DIR}/seoul_population_cleaned.csv"

    opportunity_matrix = pd.read_csv(matrix_path)
    population = pd.read_csv(population_path)
    features = build_feature_table(opportunity_matrix, population)
    feature_path = save_csv(features, f"{OUTPUT_TABLE_DIR}/seoul_feature_table.csv")

    print(f"feature table 저장: {feature_path}")
    print(features.head())


if __name__ == "__main__":
    main()
