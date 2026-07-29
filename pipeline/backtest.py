"""Walk-forward backtest and output JSON generation."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import (
    BACKTEST_SEASON,
    CHAMPIONSHIP_NOTES,
    CONSTRUCTOR_CHAMPIONSHIP_DSQ,
    CURRENT_SEASON,
    DRIVER_CHAMPIONSHIP_DSQ,
    DRIVERS_BEST_N_RESULTS,
    DRIVERS_SPLIT_BEST_N,
    LEADERBOARD_SEASONS,
    OUTPUTS_DIR,
    POINTS_SYSTEM,
    RACES_2026,
    get_team_color,
    normalize_team,
)
from features import FEATURE_COLS, build_features, build_upcoming_features, load_features
from model import RaceRanker, load_model, train_full_model
from points_rules import race_points_system_label

logger = logging.getLogger(__name__)


def _mean_position_error(pred: pd.DataFrame, actual: pd.DataFrame) -> float:
    merged = pred.merge(actual, on="driver_key", suffixes=("_pred", "_actual"))
    if merged.empty:
        return float("nan")
    return float(np.mean(np.abs(merged["predicted_position"] - merged["finish_position"])))


def _podium_hit_rate(pred: pd.DataFrame, actual: pd.DataFrame) -> float:
    actual_podium = set(actual[actual["finish_position"] <= 3]["driver_key"])
    pred_podium = set(pred[pred["predicted_position"] <= 3]["driver_key"])
    if not actual_podium:
        return 0.0
    return len(actual_podium & pred_podium) / len(actual_podium)


def _winner_hit(pred: pd.DataFrame, actual: pd.DataFrame) -> bool:
    pred_winner = pred.loc[pred["predicted_position"].idxmin(), "driver_key"] if len(pred) else None
    actual_winner = actual.loc[actual["finish_position"].idxmin(), "driver_key"] if len(actual) else None
    return pred_winner == actual_winner


def _spearman(pred: pd.DataFrame, actual: pd.DataFrame) -> float:
    merged = pred.merge(actual, on="driver_key")
    if len(merged) < 3:
        return float("nan")
    corr, _ = spearmanr(merged["predicted_position"], merged["finish_position"])
    return float(corr) if not np.isnan(corr) else 0.0


# Map event names to a short country/location label for chart axes.
_EVENT_SHORT: dict[str, str] = {
    "Australian": "Australia",
    "Chinese": "China",
    "Japanese": "Japan",
    "Bahrain": "Bahrain",
    "Saudi Arabian": "Saudi Arabia",
    "Miami": "Miami",
    "Emilia Romagna": "Imola",
    "Monaco": "Monaco",
    "Canadian": "Canada",
    "Spanish": "Spain",
    "Barcelona": "Spain",
    "Austrian": "Austria",
    "British": "Britain",
    "Hungarian": "Hungary",
    "Belgian": "Belgium",
    "Dutch": "Netherlands",
    "Italian": "Italy",
    "Azerbaijan": "Azerbaijan",
    "Singapore": "Singapore",
    "United States": "USA",
    "United States West": "US West",
    "Mexico City": "Mexico",
    "Mexican": "Mexico",
    "São Paulo": "Brazil",
    "Sao Paulo": "Brazil",
    "Brazilian": "Brazil",
    "Las Vegas": "Las Vegas",
    "Qatar": "Qatar",
    "Abu Dhabi": "Abu Dhabi",
    # 2020–2021 calendar extras / one-offs
    "Styrian": "Styria",
    "70th Anniversary": "70th Anniv.",
    "Tuscan": "Tuscany",
    "Eifel": "Eifel",
    "Portuguese": "Portugal",
    "Sakhir": "Sakhir",
    "Turkish": "Turkey",
    "Russian": "Russia",
    "French": "France",
    "German": "Germany",
    "Malaysian": "Malaysia",
    "European": "Europe",
    "Korean": "Korea",
    "Indian": "India",
    "San Marino": "San Marino",
    "Pacific": "Pacific",
    "Argentine": "Argentina",
    "South African": "South Africa",
    "Luxembourg": "Luxembourg",
}


def _short_event(name: str) -> str:
    """Compact country/location label for chart axes (drop 'Grand Prix')."""
    if not name:
        return ""
    base = " ".join(name.replace("Grand Prix", "").split()).strip()
    return _EVENT_SHORT.get(base, base)


def _norm_match(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def _is_driver_dsq(season: int, name: str) -> bool:
    targets = DRIVER_CHAMPIONSHIP_DSQ.get(season, ())
    n = _norm_match(name)
    return any(t in n or n == t for t in targets)


def _is_constructor_dsq(season: int, team: str) -> bool:
    targets = CONSTRUCTOR_CHAMPIONSHIP_DSQ.get(season, ())
    n = _norm_match(normalize_team(team))
    return any(t == n or t in n for t in targets)


def _round_pts(value: float) -> float:
    return round(float(value), 1)


def _kept_best_n(results: list[tuple[str, float]], best_n: int) -> set[str]:
    if best_n <= 0 or not results:
        return set()
    ranked = sorted(enumerate(results), key=lambda ix: (-ix[1][1], ix[0]))
    return {results[i][0] for i, _ in ranked[:best_n]}


def _race_total_and_keep(
    race_results: list[tuple[str, float]],
    *,
    best_n: int | None = None,
    split: tuple[int, int, int] | None = None,
) -> tuple[float, set[str] | None]:
    """Return (counting total, keep set). keep set is None when all races count."""
    if not race_results:
        return 0.0, None
    if split is not None:
        first_size, best_first, best_second = split
        first = race_results[:first_size]
        second = race_results[first_size:]
        keep = _kept_best_n(first, best_first) | _kept_best_n(second, best_second)
        total = sum(p for sid, p in race_results if sid in keep)
        return _round_pts(total), keep
    if best_n is not None:
        keep = _kept_best_n(race_results, best_n)
        total = sum(p for sid, p in race_results if sid in keep)
        return _round_pts(total), keep
    return _round_pts(sum(p for _, p in race_results)), None


def _accumulate_points(
    key: str,
    stages: list[dict],
    race_map: dict,
    sprint_map: dict,
    *,
    best_n: int | None = None,
    split: tuple[int, int, int] | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Progressive cumulative points, optionally with drivers' dropped-scores rules.

    Returns (points_by_stage, excluded_stage_ids) where exclusions are race stages
    whose points do not count in the *final* championship total.
    """
    race_results: list[tuple[str, float]] = []  # (stage_id, points) in order
    sprint_cum = 0.0
    pts: dict[str, float] = {}

    for st in stages:
        rnd = st["round"]
        src = sprint_map if st["kind"] == "sprint" else race_map
        gained = _round_pts(float(src.get(rnd, {}).get(key, 0.0) or 0.0))
        if st["kind"] == "sprint":
            sprint_cum = _round_pts(sprint_cum + gained)
        else:
            race_results.append((st["id"], gained))

        race_total, _ = _race_total_and_keep(race_results, best_n=best_n, split=split)
        pts[st["id"]] = _round_pts(race_total + sprint_cum)

    _, keep = _race_total_and_keep(race_results, best_n=best_n, split=split)
    excluded: list[str] = []
    if keep is not None:
        excluded = [sid for sid, _ in race_results if sid not in keep]

    return pts, excluded


def build_leaderboard_from_sessions(
    sessions: pd.DataFrame,
    season: int,
    *,
    counting_season: int | None = None,
    race_points_from_year: int | None = None,
) -> dict:
    """Progressive cumulative championship points (race + sprint) for a season.

    Uses the real ``Points`` values from FastF1 (race and sprint sessions), so
    sprint results are included and all classified drivers appear.
    """
    if sessions is None or sessions.empty:
        return {"season": season, "rounds": [], "race_names": {}, "drivers": [], "constructors": []}

    scoring = sessions[
        (sessions["year"] == season) & (sessions["session"].isin(["R", "S"]))
    ].copy()
    scoring = scoring[scoring["position"].notna()]
    if scoring.empty:
        return {"season": season, "rounds": [], "race_names": {}, "drivers": [], "constructors": []}

    scoring["points"] = pd.to_numeric(scoring["points"], errors="coerce").fillna(0.0)
    scoring["driver_key"] = scoring["driver_code"].fillna("").astype(str)
    scoring["team_norm"] = scoring["team"].fillna("").apply(normalize_team)

    rounds_sorted = sorted(int(r) for r in scoring["round"].unique())
    race_names = {
        str(rnd): (
            scoring[scoring["round"] == rnd]["event_name"].dropna().iloc[0]
            if scoring[scoring["round"] == rnd]["event_name"].notna().any()
            else RACES_2026.get(rnd, f"Round {rnd}")
        )
        for rnd in rounds_sorted
    }

    # Split points by session so sprints can be shown as their own step that
    # happens *before* the main race of a sprint weekend.
    def _nested(df: pd.DataFrame, key_col: str) -> dict[int, dict[str, float]]:
        out: dict[int, dict[str, float]] = {}
        if df.empty:
            return out
        grp = df.groupby(["round", key_col])["points"].sum().reset_index()
        for _, r in grp.iterrows():
            out.setdefault(int(r["round"]), {})[str(r[key_col])] = _round_pts(float(r["points"]))
        return out

    race_scoring = scoring[scoring["session"] == "R"]
    sprint_scoring = scoring[scoring["session"] == "S"]
    race_d = _nested(race_scoring, "driver_key")
    sprint_d = _nested(sprint_scoring, "driver_key")
    race_t = _nested(race_scoring, "team_norm")
    sprint_t = _nested(sprint_scoring, "team_norm")
    sprint_rounds = {int(r) for r in sprint_scoring["round"].unique()}

    # Ordered stages: for a sprint weekend, sprint step precedes the race step.
    stages: list[dict] = []
    for rnd in rounds_sorted:
        short = _short_event(race_names[str(rnd)])
        if rnd in sprint_rounds:
            stages.append({"id": f"{rnd}S", "round": rnd, "kind": "sprint", "label": f"{short} S"})
        stages.append({"id": str(rnd), "round": rnd, "kind": "race", "label": short})

    counting_year = counting_season if counting_season is not None else season
    drivers_best_n = DRIVERS_BEST_N_RESULTS.get(counting_year)
    drivers_split = DRIVERS_SPLIT_BEST_N.get(counting_year)
    race_points_year = race_points_from_year if race_points_from_year is not None else season

    # Latest known name/team per driver
    driver_meta: dict[str, dict] = {}
    for key, grp in scoring.sort_values(["round"]).groupby("driver_key"):
        last = grp.iloc[-1]
        driver_meta[key] = {
            "code": key,
            "name": last.get("driver_name") or key,
            "team": last.get("team_norm") or "",
        }

    last_stage = stages[-1]["id"] if stages else None

    # Race finishing positions only (FIA Art. 7.2 — sprints do not count for ties).
    # Drivers: { "round": position }. Constructors: { "round": [pos, pos, ...] }.
    driver_race_pos: dict[str, dict[str, int]] = {}
    constructor_race_pos: dict[str, dict[str, list[int]]] = {}
    if not race_scoring.empty:
        for _, row in race_scoring.iterrows():
            key = str(row["driver_key"])
            team = str(row["team_norm"] or "")
            rnd = str(int(row["round"]))
            try:
                pos = int(row["position"])
            except (TypeError, ValueError):
                continue
            if pos <= 0:
                continue
            driver_race_pos.setdefault(key, {})[rnd] = pos
            if team:
                constructor_race_pos.setdefault(team, {}).setdefault(rnd, []).append(pos)
        for team, by_rnd in constructor_race_pos.items():
            for rnd, positions in by_rnd.items():
                by_rnd[rnd] = sorted(positions)

    def _place_counts(positions: dict, upto_rounds: set[int] | None = None) -> list[int]:
        """Histogram of finishing places (index 0 = P1 count)."""
        counts: list[int] = []
        for rnd_str, val in positions.items():
            if upto_rounds is not None and int(rnd_str) not in upto_rounds:
                continue
            vals = val if isinstance(val, list) else [val]
            for p in vals:
                idx = int(p) - 1
                if idx < 0:
                    continue
                while len(counts) <= idx:
                    counts.append(0)
                counts[idx] += 1
        return counts

    def _f1_sort_key(entity: dict) -> tuple:
        pts = float(entity["points_by_round"].get(last_stage, 0) or 0)
        # Negate counts so lexicographic ascending sort ranks better results first.
        counts = _place_counts(entity.get("race_positions") or {})
        return (-pts, tuple(-c for c in counts), entity.get("name") or "")

    try:
        from assets import image_for_driver
    except Exception:
        image_for_driver = lambda _c, _n=None: None  # noqa: E731

    drivers_out = []
    for key, meta in driver_meta.items():
        points_by_round, excluded = _accumulate_points(
            key,
            stages,
            race_d,
            sprint_d,
            best_n=drivers_best_n,
            split=drivers_split,
        )
        drivers_out.append(
            {
                "code": key,
                "name": meta["name"],
                "team": meta["team"],
                "color": get_team_color(meta["team"]),
                "image": image_for_driver(key, meta["name"]),
                "points_by_round": points_by_round,
                "excluded_stages": excluded,
                "disqualified": _is_driver_dsq(season, str(meta["name"])),
                "race_positions": driver_race_pos.get(key, {}),
            }
        )

    all_teams = sorted(t for t in scoring["team_norm"].unique() if t)
    constructors_out = []
    for team in all_teams:
        points_by_round, _ = _accumulate_points(team, stages, race_t, sprint_t, best_n=None)
        constructors_out.append(
            {
                "name": team,
                "color": get_team_color(team),
                "points_by_round": points_by_round,
                "disqualified": _is_constructor_dsq(season, team),
                "race_positions": constructor_race_pos.get(team, {}),
            }
        )

    # Sort by final standings with F1 dead-heat tiebreakers (Art. 7.2).
    # DSQ entries stay in points order so their chart placement is unchanged.
    drivers_out.sort(key=_f1_sort_key)
    constructors_out.sort(key=_f1_sort_key)

    notes: list[str] = []
    scoring_rule = None
    if drivers_split is not None:
        first_size, best_first, best_second = drivers_split
        split_note = (
            f"Only each driver's best {best_first} results from the first {first_size} races "
            f"and best {best_second} from the remaining races counted toward the championship. "
            "Grey markers show results that were dropped. "
            "Constructors counted all results."
        )
        scoring_rule = {
            "best_n": best_first + best_second,
            "applies_to": "drivers",
            "note": split_note,
        }
        notes.append(split_note)
    elif drivers_best_n is not None:
        best_n_note = (
            f"Only each driver's best {drivers_best_n} race results counted toward the championship. "
            "Grey markers show results that were dropped. "
            "Constructors counted all results."
        )
        scoring_rule = {
            "best_n": drivers_best_n,
            "applies_to": "drivers",
            "note": best_n_note,
        }
        notes.append(best_n_note)
    if scoring_rule is not None:
        notes[0] = f"Race points: {race_points_system_label(race_points_year)}. {notes[0]}"
    notes.extend(CHAMPIONSHIP_NOTES.get(season, []))

    result = {
        "season": season,
        "rounds": rounds_sorted,
        "stages": stages,
        "race_names": race_names,
        "scoring_rule": scoring_rule,
        "notes": notes,
        "drivers": drivers_out,
        "constructors": constructors_out,
    }
    from season_stats import build_season_stats

    result["stats"] = build_season_stats(sessions, season, result)
    return result


def _build_leaderboard(race_results: list[dict], season: int) -> dict:
    """Fallback leaderboard from race payloads (mock path, race points only)."""
    driver_points: dict[str, dict] = {}
    constructor_points: dict[str, dict] = {}

    rounds_sorted = sorted(race_results, key=lambda r: r["round"])
    all_drivers: set[str] = set()
    all_teams: set[str] = set()

    for race in rounds_sorted:
        for d in race.get("actual", []):
            all_drivers.add(d["driver_code"])
            all_teams.add(normalize_team(d.get("team", "")))

    for code in all_drivers:
        driver_points[code] = {"name": code, "team": "", "color": "#888", "points_by_round": {}}
    for team in all_teams:
        constructor_points[team] = {"name": team, "color": get_team_color(team), "points_by_round": {}}

    cumulative_d: dict[str, int] = {c: 0 for c in all_drivers}
    cumulative_c: dict[str, int] = {t: 0 for t in all_teams}

    for race in rounds_sorted:
        rnd = race["round"]
        actual_sorted = sorted(race.get("actual", []), key=lambda x: x.get("position", 99))
        for i, d in enumerate(actual_sorted):
            pos = d.get("position", i + 1)
            pts = POINTS_SYSTEM[pos - 1] if pos <= len(POINTS_SYSTEM) else 0
            code = d["driver_code"]
            team = normalize_team(d.get("team", ""))
            cumulative_d[code] = cumulative_d.get(code, 0) + pts
            cumulative_c[team] = cumulative_c.get(team, 0) + pts
            driver_points.setdefault(code, {"name": d.get("name", code), "team": team, "color": get_team_color(team), "points_by_round": {}})
            driver_points[code]["name"] = d.get("name", code)
            driver_points[code]["team"] = team
            driver_points[code]["color"] = get_team_color(team)
            driver_points[code]["points_by_round"][str(rnd)] = cumulative_d[code]

        for team in all_teams:
            constructor_points[team]["points_by_round"][str(rnd)] = cumulative_c.get(team, 0)

    return {
        "season": season,
        "rounds": [r["round"] for r in rounds_sorted],
        "stages": [
            {
                "id": str(r["round"]),
                "round": r["round"],
                "kind": "race",
                "label": _short_event(r.get("event_name", "")),
            }
            for r in rounds_sorted
        ],
        "race_names": {str(r["round"]): r.get("event_name", "") for r in rounds_sorted},
        "drivers": list(driver_points.values()),
        "constructors": list(constructor_points.values()),
    }


def _write_upcoming_prediction(
    features: pd.DataFrame,
    sessions,
    season: int,
    completed_rounds: list[int],
) -> None:
    """Train on all completed data and predict the next upcoming round."""
    if not completed_rounds:
        return

    next_round = int(max(completed_rounds)) + 1
    if next_round not in RACES_2026:
        logger.info("No upcoming round beyond completed schedule")
        return

    upcoming_feat = build_upcoming_features(sessions=sessions, features=features, season=season, round_num=next_round)
    if upcoming_feat.empty:
        logger.warning("Could not build upcoming features for round %d", next_round)
        return

    ranker = load_model()
    if ranker.model is None:
        ranker = train_full_model(features)
    preds = ranker.predict_race(upcoming_feat)

    pred_list = []
    for _, row in preds.iterrows():
        pred_list.append(
            {
                "driver_code": row["driver_key"],
                "driver_name": row["driver_name"],
                "team": normalize_team(str(row["team"])),
                "predicted_position": int(row["predicted_position"]),
                "confidence": round(float(row["confidence"]), 4),
            }
        )

    event_name = upcoming_feat["event_name"].iloc[0] if "event_name" in upcoming_feat.columns else RACES_2026.get(next_round, "")

    payload = {
        "round": next_round,
        "season": season,
        "event_name": event_name,
        "upcoming": True,
        "predictions": pred_list,
    }

    pred_path = os.path.join(OUTPUTS_DIR, f"predictions_{next_round}.json")
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Wrote upcoming prediction for %d R%d", season, next_round)


def generate_mock_data() -> None:
    """Generate sensible fallback outputs when FastF1 ingest unavailable."""
    Path(OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)

    from assets import FALLBACK_DRIVERS_2026

    drivers = FALLBACK_DRIVERS_2026
    n_rounds = 4  # mock first 4 rounds of 2026

    race_results = []
    overall_metrics = {"spearman": [], "podium_hit_rate": [], "mean_position_error": [], "winner_hits": 0}

    for rnd in range(1, n_rounds + 1):
        # Shuffle with slight bias by driver index for realism
        order = list(range(len(drivers)))
        np.random.seed(2026 + rnd)
        np.random.shuffle(order)

        predictions = []
        actual = []
        for pred_pos, idx in enumerate(order, 1):
            d = drivers[idx]
            actual_pos = pred_pos + np.random.randint(-2, 3)
            actual_pos = max(1, min(len(drivers), actual_pos))
            predictions.append(
                {
                    "driver_code": d["code"],
                    "driver_name": d["name"],
                    "team": normalize_team(d["team"]),
                    "predicted_position": pred_pos,
                    "confidence": round(1.0 / len(drivers) + np.random.random() * 0.05, 4),
                }
            )
            actual.append(
                {
                    "driver_code": d["code"],
                    "name": d["name"],
                    "team": normalize_team(d["team"]),
                    "position": actual_pos,
                }
            )

        # Re-rank actual positions uniquely
        actual.sort(key=lambda x: x["position"])
        used = set()
        for i, a in enumerate(actual):
            while a["position"] in used:
                a["position"] += 1
            used.add(a["position"])

        pred_df = pd.DataFrame(predictions)
        actual_df = pd.DataFrame(actual).rename(columns={"position": "finish_position", "driver_code": "driver_key"})
        actual_df["driver_key"] = actual_df["driver_key"]
        pred_df["driver_key"] = pred_df["driver_code"]

        spearman = _spearman(pred_df, actual_df.rename(columns={"finish_position": "finish_position"}))
        mpe = _mean_position_error(pred_df, actual_df.rename(columns={"driver_key": "driver_key", "finish_position": "finish_position"}))
        podium = _podium_hit_rate(pred_df, actual_df.rename(columns={"driver_key": "driver_key", "finish_position": "finish_position"}))
        winner = _winner_hit(pred_df, actual_df.rename(columns={"driver_key": "driver_key", "finish_position": "finish_position"}))

        race_payload = {
            "round": rnd,
            "season": CURRENT_SEASON,
            "event_name": RACES_2026.get(rnd, f"Round {rnd}"),
            "metrics": {
                "spearman": round(spearman, 4) if not np.isnan(spearman) else 0,
                "podium_hit_rate": round(podium, 4),
                "mean_position_error": round(mpe, 4) if not np.isnan(mpe) else 0,
                "winner_correct": winner,
            },
            "predictions": predictions,
            "actual": actual,
        }
        race_results.append(race_payload)

        overall_metrics["spearman"].append(spearman)
        overall_metrics["podium_hit_rate"].append(podium)
        overall_metrics["mean_position_error"].append(mpe)
        if winner:
            overall_metrics["winner_hits"] += 1

        pred_path = os.path.join(OUTPUTS_DIR, f"predictions_{rnd}.json")
        with open(pred_path, "w", encoding="utf-8") as f:
            json.dump(race_payload, f, indent=2)

    backtest = {
        "season": BACKTEST_SEASON,
        "races": race_results,
        "summary": {
            "races_evaluated": len(race_results),
            "mean_spearman": round(float(np.nanmean(overall_metrics["spearman"])), 4),
            "mean_podium_hit_rate": round(float(np.nanmean(overall_metrics["podium_hit_rate"])), 4),
            "mean_position_error": round(float(np.nanmean(overall_metrics["mean_position_error"])), 4),
            "winner_hit_rate": round(overall_metrics["winner_hits"] / max(len(race_results), 1), 4),
            "note": "Mock data — run full ingest + precompute for real backtest results",
        },
    }
    with open(os.path.join(OUTPUTS_DIR, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump(backtest, f, indent=2)

    from ingest import load_sessions

    sessions = load_sessions()
    leaderboard = build_all_leaderboards(sessions)
    # Mock path may have no sessions yet — fall back to single-season mock standings
    if not leaderboard.get("seasons"):
        leaderboard = {"seasons": {str(BACKTEST_SEASON): _build_leaderboard(race_results, BACKTEST_SEASON)}}
    with open(os.path.join(OUTPUTS_DIR, "leaderboard.json"), "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, indent=2)

    try:
        from whatif import write_formula15_leaderboards

        write_formula15_leaderboards(sessions)
    except Exception as exc:
        logger.warning("Formula 1.5 write skipped: %s", exc)

    logger.info("Generated mock backtest data for %d rounds", n_rounds)


def run_backtest(features: pd.DataFrame | None = None, season: int = BACKTEST_SEASON) -> dict:
    """Walk-forward backtest for target season."""
    Path(OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)

    if features is None:
        features = load_features()

    if features.empty or len(features[features["year"] == season]) == 0:
        logger.warning("No features for season %d, generating mock data", season)
        generate_mock_data()
        with open(os.path.join(OUTPUTS_DIR, "backtest.json"), encoding="utf-8") as f:
            return json.load(f)

    season_races = sorted(features[features["year"] == season]["round"].unique())
    race_results = []
    summary_spearman = []
    summary_podium = []
    summary_mpe = []
    winner_hits = 0

    for rnd in season_races:
        logger.info("Backtesting %d round %d", season, rnd)
        train = features[(features["year"] < season) | ((features["year"] == season) & (features["round"] < rnd))]
        ranker = RaceRanker()
        if not ranker.train_or_skip(train):
            logger.warning("Skipping round %d — insufficient training data", rnd)
            continue
        race_feat = features[(features["year"] == season) & (features["round"] == rnd)].copy()
        if race_feat.empty:
            continue

        preds = ranker.predict_race(race_feat)
        actual = race_feat[["driver_key", "driver_name", "team", "finish_position", "event_name"]].copy()

        spearman = _spearman(
            preds.rename(columns={"driver_key": "driver_key"}),
            actual.rename(columns={"driver_key": "driver_key"}),
        )
        mpe = _mean_position_error(preds, actual.rename(columns={"finish_position": "finish_position"}))
        podium = _podium_hit_rate(preds, actual.rename(columns={"finish_position": "finish_position"}))
        winner = _winner_hit(preds, actual.rename(columns={"finish_position": "finish_position"}))

        event_name = race_feat["event_name"].iloc[0] if "event_name" in race_feat.columns else RACES_2026.get(int(rnd), "")

        pred_list = []
        for _, row in preds.iterrows():
            pred_list.append(
                {
                    "driver_code": row["driver_key"],
                    "driver_name": row["driver_name"],
                    "team": normalize_team(str(row["team"])),
                    "predicted_position": int(row["predicted_position"]),
                    "confidence": round(float(row["confidence"]), 4),
                }
            )

        actual_list = []
        for _, row in actual.iterrows():
            actual_list.append(
                {
                    "driver_code": row["driver_key"],
                    "name": row["driver_name"],
                    "team": normalize_team(str(row["team"])),
                    "position": int(row["finish_position"]),
                }
            )

        race_payload = {
            "round": int(rnd),
            "season": season,
            "event_name": event_name,
            "metrics": {
                "spearman": round(spearman, 4) if not np.isnan(spearman) else 0,
                "podium_hit_rate": round(podium, 4),
                "mean_position_error": round(mpe, 4) if not np.isnan(mpe) else 0,
                "winner_correct": winner,
            },
            "predictions": pred_list,
            "actual": actual_list,
        }
        race_results.append(race_payload)

        pred_path = os.path.join(OUTPUTS_DIR, f"predictions_{int(rnd)}.json")
        with open(pred_path, "w", encoding="utf-8") as f:
            json.dump(race_payload, f, indent=2)

        summary_spearman.append(spearman)
        summary_podium.append(podium)
        summary_mpe.append(mpe)
        if winner:
            winner_hits += 1

    backtest = {
        "season": season,
        "races": race_results,
        "summary": {
            "races_evaluated": len(race_results),
            "mean_spearman": round(float(np.nanmean(summary_spearman)), 4) if summary_spearman else 0,
            "mean_podium_hit_rate": round(float(np.nanmean(summary_podium)), 4) if summary_podium else 0,
            "mean_position_error": round(float(np.nanmean(summary_mpe)), 4) if summary_mpe else 0,
            "winner_hit_rate": round(winner_hits / max(len(race_results), 1), 4),
        },
    }
    with open(os.path.join(OUTPUTS_DIR, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump(backtest, f, indent=2)

    from ingest import load_sessions

    sessions = load_sessions()
    leaderboard = build_all_leaderboards(sessions)
    with open(os.path.join(OUTPUTS_DIR, "leaderboard.json"), "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, indent=2)

    from whatif import write_formula15_leaderboards

    write_formula15_leaderboards(sessions)

    from podiumigami import write_podiumigami

    write_podiumigami(sessions)

    # Train final model on all data through latest round for /predict endpoint
    train_full_model(features)

    _write_upcoming_prediction(features, sessions, season, [int(r) for r in season_races])

    logger.info("Backtest complete: %d races", len(race_results))
    return backtest


def build_all_leaderboards(sessions: pd.DataFrame | None = None, seasons: list[int] | None = None) -> dict:
    """Build progressive leaderboards for every configured season."""
    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()
    seasons = seasons or LEADERBOARD_SEASONS
    out: dict[str, dict] = {}
    for year in seasons:
        lb = build_leaderboard_from_sessions(sessions, year)
        if lb["drivers"]:
            out[str(year)] = lb
            logger.info(
                "Leaderboard %d: %d drivers, %d stages",
                year,
                len(lb["drivers"]),
                len(lb.get("stages", [])),
            )
        else:
            logger.warning("No leaderboard data for %d", year)
    return {"seasons": out}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backtest()
