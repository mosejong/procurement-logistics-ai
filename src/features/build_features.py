import pandas as pd


def _safe_per_10k(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Return a per-10,000 rate while avoiding divide-by-zero noise."""
    denominator = pd.to_numeric(denominator, errors="coerce").replace(0, pd.NA)
    numerator = pd.to_numeric(numerator, errors="coerce").fillna(0)
    return (numerator / denominator * 10000).fillna(0).round(4)


def build_feature_table(
    opportunity_matrix: pd.DataFrame,
    population_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build a feature table for recommendation/modeling.

    The current opportunity_score stays as-is. Population/household normalized
    features are added beside it so the scoring rule can be adjusted later.
    """
    features = opportunity_matrix.copy()
    if "amount_sum" not in features.columns and "total_amount" in features.columns:
        features = features.rename(columns={"total_amount": "amount_sum"})

    if population_df is None or population_df.empty:
        return features

    population = population_df.rename(
        columns={
            "district_name": "district",
            "total_population": "population",
            "total_households": "households",
        }
    )

    required_columns = {"district", "population", "households"}
    if not required_columns.issubset(population.columns):
        return features

    merged = features.merge(population[["district", "population", "households"]], on="district", how="left")

    if "bid_count" in merged.columns:
        merged["bids_per_10k_population"] = _safe_per_10k(merged["bid_count"], merged["population"])
        merged["bids_per_10k_households"] = _safe_per_10k(merged["bid_count"], merged["households"])

    if "amount_sum" in merged.columns:
        merged["amount_per_10k_population"] = _safe_per_10k(merged["amount_sum"], merged["population"])
        merged["amount_per_10k_households"] = _safe_per_10k(merged["amount_sum"], merged["households"])

    return merged
