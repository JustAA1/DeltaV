"""XGBoost learning-to-rank model for race finishing order."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb

from config import (
    CURRENT_SEASON,
    MODEL_PATH,
    PRE_REG_CYCLE_WEIGHT,
    RECENCY_DECAY,
    REG_CYCLE_START,
)
from features import FEATURE_COLS, load_features

logger = logging.getLogger(__name__)


def _race_group_sizes(df: pd.DataFrame) -> list[int]:
    return df.groupby(["year", "round"], sort=False).size().tolist()


def _season_weight(year: float) -> float:
    """Down-weight older seasons; penalize pre-reg-cycle seasons extra.

    2026 gets weight 1.0; each earlier season decays by RECENCY_DECAY, and
    seasons before the current regulation cycle are further scaled down so the
    new-car era dominates the fit.
    """
    w = RECENCY_DECAY ** (CURRENT_SEASON - year)
    if year < REG_CYCLE_START:
        w *= PRE_REG_CYCLE_WEIGHT
    return float(w)


def _group_weights(work: pd.DataFrame) -> np.ndarray:
    """One weight per race group (ranking uses per-group weights)."""
    group_years = work.groupby(["year", "round"], sort=False)["year"].first()
    return np.array([_season_weight(float(y)) for y in group_years], dtype=float)


def _prepare_matrix(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, list[int], np.ndarray]:
    work = df.dropna(subset=["finish_position"]).copy()
    work = work.sort_values(["year", "round", "driver_key"])
    for col in FEATURE_COLS:
        if col not in work.columns:
            work[col] = np.nan
        work[col] = work[col].fillna(work[col].median())

    X = work[FEATURE_COLS]
    y = work["target_score"].values.astype(float)
    groups = _race_group_sizes(work)
    weights = _group_weights(work)
    return work, X.values, y, groups, weights


class RaceRanker:
    def __init__(self) -> None:
        self.model: xgb.Booster | None = None
        self.feature_cols = FEATURE_COLS

    def train(self, df: pd.DataFrame) -> None:
        work, X, y, groups, weights = _prepare_matrix(df)
        if len(work) < 10:
            raise ValueError("Not enough training data")

        dtrain = xgb.DMatrix(X, label=y)
        dtrain.set_group(groups)
        dtrain.set_weight(weights)

        params = {
            "objective": "rank:pairwise",
            "eval_metric": "ndcg",
            "eta": 0.1,
            "max_depth": 5,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "seed": 42,
        }

        try:
            self.model = xgb.train(params, dtrain, num_boost_round=100)
        except xgb.core.XGBoostError:
            logger.warning("rank:pairwise failed, falling back to regression")
            params["objective"] = "reg:squarederror"
            self.model = xgb.train(params, dtrain, num_boost_round=100)

        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        self.model.save_model(MODEL_PATH)
        logger.info("Saved model to %s", MODEL_PATH)

    def train_or_skip(self, df: pd.DataFrame) -> bool:
        """Train if enough data; return False when training is not possible."""
        try:
            self.train(df)
            return True
        except ValueError as exc:
            logger.warning("%s", exc)
            return False

    def load(self) -> None:
        if os.path.exists(MODEL_PATH):
            self.model = xgb.Booster()
            self.model.load_model(MODEL_PATH)

    def predict_race(self, race_df: pd.DataFrame) -> pd.DataFrame:
        if self.model is None:
            self.load()
        if self.model is None:
            raise RuntimeError("Model not trained")

        work = race_df.copy()
        for col in self.feature_cols:
            if col not in work.columns:
                work[col] = np.nan
            work[col] = work[col].fillna(work[col].median() if work[col].notna().any() else 0)

        X = work[self.feature_cols].values
        dmat = xgb.DMatrix(X)
        scores = self.model.predict(dmat)

        out = work[["year", "round", "driver_key", "driver_name", "team"]].copy()
        out["score"] = scores
        out["predicted_position"] = out["score"].rank(ascending=False, method="min").astype(int)

        # Confidence from score spread (softmax-like)
        exp_s = np.exp(scores - scores.max())
        probs = exp_s / exp_s.sum()
        out["confidence"] = probs

        return out.sort_values("predicted_position")


def train_full_model(features: pd.DataFrame | None = None, before_year: int | None = None, before_round: int | None = None) -> RaceRanker:
    """Train on all data before a cutoff (for walk-forward)."""
    if features is None:
        features = load_features()
    train = features.copy()
    if before_year is not None:
        train = train[(train["year"] < before_year) | ((train["year"] == before_year) & (train["round"] < before_round))]
    ranker = RaceRanker()
    ranker.train(train)
    return ranker


def load_model() -> RaceRanker:
    r = RaceRanker()
    r.load()
    return r


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    train_full_model()
