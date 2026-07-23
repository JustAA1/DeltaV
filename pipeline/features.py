"""Leak-safe feature engineering for race predictions."""

from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

from config import CURRENT_SEASON, FEATURES_PATH, PARQUET_PATH, RACES_2026
from ingest import load_sessions

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "form_finish_3",
    "form_finish_5",
    "form_quali_3",
    "form_quali_5",
    "constructor_quali_gap",
    "constructor_race_pace",
    "race_pace_gap",
    "track_finish_avg",
    "track_quali_avg",
    "grid_penalty",
    "dnf_rate_5",
    "stint_count_avg",
    "practice_pace_gap",
]


def _is_dnf(status: str) -> bool:
    if not status:
        return False
    s = status.strip()
    if s.startswith("+") and "Lap" in s:
        return False
    return s not in ("Finished", "Lapped")


def _best_quali_time(row: pd.Series) -> float | None:
    times = [row.get("q1"), row.get("q2"), row.get("q3")]
    valid = [t for t in times if t is not None and not (isinstance(t, float) and np.isnan(t))]
    return min(valid) if valid else None


def build_race_base(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (year, round, driver) from race results."""
    race = df[df["session"] == "R"].copy()
    if race.empty:
        return pd.DataFrame()

    race = race[race["position"].notna()].copy()
    race["position"] = race["position"].astype(int)
    race["driver_key"] = race["driver_code"].fillna("").astype(str)
    race["team_norm"] = race["team"].fillna("")

    # Quali positions from Q session
    quali = df[df["session"] == "Q"].copy()
    quali_times = []
    for _, row in quali.iterrows():
        quali_times.append(
            {
                "year": row["year"],
                "round": row["round"],
                "driver_key": str(row["driver_code"] or ""),
                "quali_time": _best_quali_time(row),
                "quali_position": row["position"],
            }
        )
    quali_df = pd.DataFrame(quali_times)
    if not quali_df.empty:
        quali_df["quali_position"] = pd.to_numeric(quali_df["quali_position"], errors="coerce")
        # Derive quali position from times within race weekend
        for (y, r), grp in quali_df.groupby(["year", "round"]):
            valid = grp.dropna(subset=["quali_time"])
            if len(valid) > 0:
                ranks = valid["quali_time"].rank(method="min")
                quali_df.loc[valid.index, "quali_position"] = ranks

    race = race.merge(
        quali_df[["year", "round", "driver_key", "quali_position"]],
        on=["year", "round", "driver_key"],
        how="left",
    )
    race["quali_position"] = pd.to_numeric(race["quali_position"], errors="coerce")
    race["grid_position"] = pd.to_numeric(race["grid_position"], errors="coerce")
    race["is_dnf"] = race["status"].apply(_is_dnf).astype(int)
    # Prefer median green-flag lap (representative stint pace); fall back to best.
    race["race_median_lap"] = pd.to_numeric(race.get("median_lap_time"), errors="coerce")
    race["race_best_lap"] = pd.to_numeric(race.get("best_lap_time"), errors="coerce")
    race["race_pace_lap"] = race["race_median_lap"].fillna(race["race_best_lap"])

    # DNF-robust finishing position: a mechanical/incident DNF should not be
    # read as "slow pace". We keep the classified position for standings, but
    # expose a NaN-on-DNF version so pace-form features ignore retirements.
    # Reliability is captured separately by dnf_rate.
    race["finish_position_clean"] = race["position"].where(race["is_dnf"] == 0)

    return race[
        [
            "year",
            "round",
            "event_name",
            "circuit",
            "driver_key",
            "driver_name",
            "driver_number",
            "team_norm",
            "position",
            "finish_position_clean",
            "quali_position",
            "grid_position",
            "is_dnf",
            "status",
            "race_pace_lap",
        ]
    ].rename(columns={"team_norm": "team", "position": "finish_position"})


def _rolling_driver_feature(race_df: pd.DataFrame, col: str, window: int, out_col: str) -> pd.Series:
    """Shifted rolling mean per driver (no leakage)."""
    race_df = race_df.sort_values(["driver_key", "year", "round"])
    shifted = race_df.groupby("driver_key")[col].shift(1)
    rolled = (
        shifted.groupby(race_df["driver_key"])
        .rolling(window, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return rolled.rename(out_col)


def _constructor_quali_gap(df: pd.DataFrame, quali_df: pd.DataFrame) -> pd.Series:
    """Team avg quali gap to pole, rolling over prior races."""
    if quali_df.empty:
        return pd.Series(np.nan, index=df.index)

    gaps = []
    for _, row in quali_df.iterrows():
        y, r, team = row["year"], row["round"], row["team"]
        weekend = quali_df[(quali_df["year"] == y) & (quali_df["round"] == r)]
        pole_time = weekend["quali_time"].min()
        team_laps = weekend[weekend["team"] == team]
        if pd.isna(pole_time) or team_laps.empty:
            gaps.append(np.nan)
        else:
            team_best = team_laps["quali_time"].min()
            gaps.append(team_best - pole_time if pd.notna(team_best) else np.nan)
    quali_df = quali_df.copy()
    quali_df["team_gap"] = gaps

    quali_df = quali_df.sort_values(["team", "year", "round"])
    quali_df["constructor_quali_gap"] = (
        quali_df.groupby("team")["team_gap"].shift(1).groupby(quali_df["team"]).rolling(5, min_periods=1).mean().reset_index(level=0, drop=True)
    )

    merged = df.merge(
        quali_df[["year", "round", "team", "constructor_quali_gap"]],
        on=["year", "round", "team"],
        how="left",
    )
    return merged["constructor_quali_gap"]


def _race_pace_features(race_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """DNF-robust driver and constructor race pace.

    Uses the best lap set *during the race* (available even when a car later
    retires) versus the fastest race lap of the weekend, rolled over prior
    races. Because it is pace-based rather than classification-based, a
    mechanical DNF does not make a fast car look slow.
    """
    df = race_df.copy()
    if "race_pace_lap" not in df.columns or df["race_pace_lap"].notna().sum() == 0:
        nan = pd.Series(np.nan, index=race_df.index)
        return nan, nan.copy()

    # Compare each car's representative race lap to the fastest such lap that
    # weekend, so the gap reflects sustained race pace rather than a one-off lap.
    df["weekend_race_best"] = df.groupby(["year", "round"])["race_pace_lap"].transform("min")
    df["race_gap"] = df["race_pace_lap"] - df["weekend_race_best"]

    # Drop pace from races the driver retired from: a damaged or short-running
    # car leaves an unrepresentative median lap that would pollute the average.
    if "is_dnf" in df.columns:
        df.loc[df["is_dnf"] == 1, "race_gap"] = np.nan

    driver_roll = _rolling_driver_feature(df, "race_gap", 5, "race_pace_gap")

    team_gap = df.groupby(["year", "round", "team"])["race_gap"].mean().reset_index()
    team_gap = team_gap.sort_values(["team", "year", "round"])
    team_gap["constructor_race_pace"] = (
        team_gap.groupby("team")["race_gap"]
        .shift(1)
        .groupby(team_gap["team"])
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    merged = race_df.merge(
        team_gap[["year", "round", "team", "constructor_race_pace"]],
        on=["year", "round", "team"],
        how="left",
    )
    return driver_roll, merged["constructor_race_pace"]


def _track_history(race_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Driver mean finish/quali at circuit from prior visits only."""
    race_df = race_df.sort_values(["driver_key", "circuit", "year", "round"])
    finish_col = "finish_position_clean" if "finish_position_clean" in race_df.columns else "finish_position"
    finish_avg = (
        race_df.groupby(["driver_key", "circuit"])[finish_col]
        .apply(lambda s: s.shift(1).expanding().mean())
        .reset_index(level=[0, 1], drop=True)
    )
    quali_avg = (
        race_df.groupby(["driver_key", "circuit"])["quali_position"]
        .apply(lambda s: s.shift(1).expanding().mean())
        .reset_index(level=[0, 1], drop=True)
    )
    return finish_avg, quali_avg


def _practice_pace(df_sessions: pd.DataFrame, race_df: pd.DataFrame) -> pd.Series:
    """Best FP1-3 lap vs session best for same weekend (pre-race signal)."""
    practice = df_sessions[df_sessions["session"].isin(["FP1", "FP2", "FP3"])].copy()
    if practice.empty:
        return pd.Series(np.nan, index=race_df.index)

    practice = practice.dropna(subset=["best_lap_time"])
    session_best = practice.groupby(["year", "round", "session"])["best_lap_time"].min().reset_index()
    session_best = session_best.rename(columns={"best_lap_time": "session_best"})

    driver_best = (
        practice.groupby(["year", "round", "driver_code"])["best_lap_time"]
        .min()
        .reset_index()
        .rename(columns={"driver_code": "driver_key", "best_lap_time": "driver_best"})
    )

    # Weekend-level: min across FP sessions
    weekend_driver = driver_best.groupby(["year", "round", "driver_key"])["driver_best"].min().reset_index()
    weekend_best = practice.groupby(["year", "round"])["best_lap_time"].min().reset_index()
    weekend_best = weekend_best.rename(columns={"best_lap_time": "weekend_best"})

    merged = weekend_driver.merge(weekend_best, on=["year", "round"])
    merged["practice_pace_gap"] = merged["driver_best"] - merged["weekend_best"]

    out = race_df.merge(
        merged[["year", "round", "driver_key", "practice_pace_gap"]],
        on=["year", "round", "driver_key"],
        how="left",
    )
    return out["practice_pace_gap"]


def _tire_strategy(df_sessions: pd.DataFrame, race_df: pd.DataFrame) -> pd.Series:
    """Rolling avg stint count from prior races."""
    race_laps = df_sessions[(df_sessions["session"] == "R") & df_sessions["stint_count"].notna()].copy()
    if race_laps.empty:
        return pd.Series(np.nan, index=race_df.index)

    stint = race_laps.groupby(["year", "round", "driver_code"])["stint_count"].first().reset_index()
    stint = stint.rename(columns={"driver_code": "driver_key"})
    stint = stint.sort_values(["driver_key", "year", "round"])
    stint["stint_count_avg"] = (
        stint.groupby("driver_key")["stint_count"]
        .shift(1)
        .groupby(stint["driver_key"])
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    out = race_df.merge(stint[["year", "round", "driver_key", "stint_count_avg"]], on=["year", "round", "driver_key"], how="left")
    return out["stint_count_avg"]


def build_features(sessions: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build full feature matrix."""
    if sessions is None:
        sessions = load_sessions()
    if sessions.empty:
        logger.warning("No session data for features")
        return pd.DataFrame()

    race_df = build_race_base(sessions)
    if race_df.empty:
        return pd.DataFrame()

    race_df = race_df.sort_values(["year", "round", "driver_key"]).reset_index(drop=True)

    # Form uses the DNF-robust finish (retirements excluded) so a mechanical
    # DNF does not drag a fast car's pace signal down.
    race_df["form_finish_3"] = _rolling_driver_feature(race_df, "finish_position_clean", 3, "form_finish_3")
    race_df["form_finish_5"] = _rolling_driver_feature(race_df, "finish_position_clean", 5, "form_finish_5")
    race_df["form_quali_3"] = _rolling_driver_feature(race_df, "quali_position", 3, "form_quali_3")
    race_df["form_quali_5"] = _rolling_driver_feature(race_df, "quali_position", 5, "form_quali_5")

    race_pace, constructor_race_pace = _race_pace_features(race_df)
    race_df["race_pace_gap"] = race_pace
    race_df["constructor_race_pace"] = constructor_race_pace

    race_df["dnf_rate_5"] = (
        race_df.groupby("driver_key")["is_dnf"]
        .shift(1)
        .groupby(race_df["driver_key"])
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    race_df["grid_penalty"] = race_df["grid_position"] - race_df["quali_position"]

    finish_track, quali_track = _track_history(race_df)
    race_df["track_finish_avg"] = finish_track
    race_df["track_quali_avg"] = quali_track

    quali_src = sessions[sessions["session"] == "Q"].copy()
    quali_rows = []
    for _, row in quali_src.iterrows():
        quali_rows.append(
            {
                "year": row["year"],
                "round": row["round"],
                "team": row["team"],
                "quali_time": _best_quali_time(row),
            }
        )
    quali_gap_df = pd.DataFrame(quali_rows)
    race_df["constructor_quali_gap"] = _constructor_quali_gap(race_df, quali_gap_df)

    race_df["practice_pace_gap"] = _practice_pace(sessions, race_df)
    race_df["stint_count_avg"] = _tire_strategy(sessions, race_df)

    # Target for ranker: higher score = better finish (invert position)
    race_df["target_score"] = race_df.groupby(["year", "round"])["finish_position"].transform(lambda x: len(x) + 1 - x)

    os.makedirs(os.path.dirname(FEATURES_PATH) or ".", exist_ok=True)
    race_df.to_parquet(FEATURES_PATH, index=False)
    logger.info("Wrote %d feature rows to %s", len(race_df), FEATURES_PATH)
    return race_df


def load_features() -> pd.DataFrame:
    if os.path.exists(FEATURES_PATH):
        return pd.read_parquet(FEATURES_PATH)
    return build_features()


def _drivers_for_round(sessions: pd.DataFrame, year: int, round_num: int) -> pd.DataFrame:
    """Resolve driver grid for a round from quali, practice, or prior race."""
    weekend = sessions[(sessions["year"] == year) & (sessions["round"] == round_num)]
    if weekend.empty:
        return pd.DataFrame()

    for ses in ("Q", "FP3", "FP2", "FP1", "R"):
        part = weekend[weekend["session"] == ses]
        if part.empty:
            continue
        drivers = (
            part.dropna(subset=["driver_code"])
            .drop_duplicates("driver_code")[
                ["driver_code", "driver_name", "driver_number", "team", "event_name", "circuit"]
            ]
            .copy()
        )
        drivers = drivers[drivers["driver_code"].astype(str).str.len() > 0]
        if not drivers.empty:
            drivers["driver_key"] = drivers["driver_code"].astype(str)
            drivers["team"] = drivers["team"].fillna("")
            return drivers

    return pd.DataFrame()


def _circuit_for_event(
    sessions: pd.DataFrame,
    features: pd.DataFrame,
    season: int,
    round_num: int,
    event_name: str,
) -> str:
    """Best-effort circuit name for an upcoming round.

    Prefers this round's own session data, then this season's schedule, then the
    most recent historical running of the same event. This avoids inheriting the
    previous round's circuit when the upcoming weekend has no data yet.
    """
    if sessions is not None and not sessions.empty and "circuit" in sessions.columns:
        this_round = sessions[
            (sessions["year"] == season) & (sessions["round"] == round_num)
        ]
        vals = this_round["circuit"].dropna().unique() if not this_round.empty else []
        if len(vals) > 0:
            return str(vals[0])

        if event_name and "event_name" in sessions.columns:
            same_event = sessions[sessions["event_name"] == event_name].sort_values("year")
            vals = same_event["circuit"].dropna().unique()
            if len(vals) > 0:
                return str(vals[-1])

    if features is not None and not features.empty and "event_name" in features.columns:
        same_event = features[features["event_name"] == event_name].sort_values(["year", "round"])
        vals = same_event["circuit"].dropna().unique() if "circuit" in same_event.columns else []
        if len(vals) > 0:
            return str(vals[-1])

    return ""


def build_upcoming_features(
    sessions: pd.DataFrame | None = None,
    features: pd.DataFrame | None = None,
    season: int = CURRENT_SEASON,
    round_num: int | None = None,
) -> pd.DataFrame:
    """Build pre-race feature rows for an uncompleted round."""
    if sessions is None:
        sessions = load_sessions()
    if features is None:
        features = load_features()
    if sessions.empty or features.empty:
        return pd.DataFrame()

    season_feat = features[features["year"] == season]
    if season_feat.empty:
        return pd.DataFrame()

    completed = sorted(season_feat["round"].unique())
    if not completed:
        return pd.DataFrame()

    if round_num is None:
        round_num = int(max(completed)) + 1

    if round_num in completed:
        return pd.DataFrame()

    if round_num not in RACES_2026:
        return pd.DataFrame()

    drivers = _drivers_for_round(sessions, season, round_num)
    if drivers.empty:
        last_round = int(max(completed))
        last_race = season_feat[season_feat["round"] == last_round]
        drivers = last_race[
            ["driver_key", "driver_name", "driver_number", "team", "event_name", "circuit"]
        ].copy()

    if drivers.empty:
        return pd.DataFrame()

    event_name = RACES_2026.get(round_num) or (
        drivers["event_name"].iloc[0] if drivers["event_name"].notna().any() else f"Round {round_num}"
    )
    # Resolve the circuit from this event's history rather than the driver list,
    # which for an un-raced round falls back to the *previous* round's circuit
    # and would corrupt track-history features.
    circuit = _circuit_for_event(sessions, features, season, round_num, event_name)
    if not circuit and "circuit" in drivers.columns and drivers["circuit"].notna().any():
        circuit = drivers["circuit"].iloc[0]

    # Prior completed features for rolling stats
    prior = season_feat[season_feat["round"] < round_num].sort_values(["driver_key", "round"])
    prior_all = features[features["year"] < season].sort_values(["driver_key", "year", "round"])

    quali_weekend = sessions[(sessions["year"] == season) & (sessions["round"] == round_num) & (sessions["session"] == "Q")]
    practice_weekend = sessions[
        (sessions["year"] == season)
        & (sessions["round"] == round_num)
        & (sessions["session"].isin(["FP1", "FP2", "FP3"]))
    ]

    rows: list[dict] = []
    for _, drv in drivers.iterrows():
        key = str(drv["driver_key"])
        hist = prior[prior["driver_key"] == key]
        hist_all = pd.concat(
            [
                prior_all[prior_all["driver_key"] == key],
                hist,
            ]
        ).sort_values(["year", "round"])

        base: dict = {
            "year": season,
            "round": round_num,
            "event_name": event_name,
            "circuit": circuit,
            "driver_key": key,
            "driver_name": drv.get("driver_name", key),
            "driver_number": drv.get("driver_number"),
            "team": drv.get("team", ""),
            "finish_position": np.nan,
            "quali_position": np.nan,
            "grid_position": np.nan,
            "is_dnf": 0,
            "status": "",
            "target_score": np.nan,
        }

        if not hist.empty:
            last = hist.iloc[-1]
            for col in [
                "form_finish_3",
                "form_finish_5",
                "form_quali_3",
                "form_quali_5",
                "dnf_rate_5",
                "stint_count_avg",
                "constructor_quali_gap",
                "constructor_race_pace",
                "race_pace_gap",
            ]:
                if col in last:
                    base[col] = last[col]

        if not hist_all.empty and circuit:
            circuit_hist = hist_all[hist_all["circuit"] == circuit]
            if not circuit_hist.empty:
                # DNF-robust: exclude retirements so an old DNF at this track
                # doesn't count as a ~last-place finish and tank the average.
                fcol = (
                    "finish_position_clean"
                    if "finish_position_clean" in circuit_hist.columns
                    else "finish_position"
                )
                base["track_finish_avg"] = circuit_hist[fcol].mean()
                base["track_quali_avg"] = circuit_hist["quali_position"].mean()

        # Quali for this weekend
        q_row = quali_weekend[quali_weekend["driver_code"].astype(str) == key]
        if not q_row.empty:
            qr = q_row.iloc[0]
            base["quali_position"] = pd.to_numeric(qr.get("position"), errors="coerce")
            base["grid_position"] = pd.to_numeric(qr.get("grid_position"), errors="coerce")
            if pd.isna(base["grid_position"]):
                base["grid_position"] = base["quali_position"]
            if pd.notna(base["quali_position"]) and pd.notna(base["grid_position"]):
                base["grid_penalty"] = base["grid_position"] - base["quali_position"]

        # Practice pace gap
        if not practice_weekend.empty:
            prac = practice_weekend[practice_weekend["driver_code"].astype(str) == key].dropna(subset=["best_lap_time"])
            if not prac.empty:
                driver_best = prac["best_lap_time"].min()
                weekend_best = practice_weekend["best_lap_time"].min()
                if pd.notna(driver_best) and pd.notna(weekend_best):
                    base["practice_pace_gap"] = driver_best - weekend_best

        for col in FEATURE_COLS:
            base.setdefault(col, np.nan)

        rows.append(base)

    if not rows:
        return pd.DataFrame()

    upcoming = pd.DataFrame(rows)
    logger.info("Built %d upcoming feature rows for %d R%d", len(upcoming), season, round_num)
    return upcoming


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_features()
