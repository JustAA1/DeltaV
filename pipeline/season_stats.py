"""Season statistics (wins, poles, podiums, DNFs) from session results."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from config import get_team_color, normalize_team


def _is_dnf(status: str) -> bool:
    s = (status or "").strip().lower()
    if not s:
        return False
    if s in ("finished", "lapped"):
        return False
    if s.startswith("+") and "lap" in s:
        return False
    return True


def _pole_holders(
    races: pd.DataFrame,
    quali: pd.DataFrame,
) -> dict[int, tuple[str, str]]:
    """round -> (driver_key, team_norm) for pole sitter."""
    poles: dict[int, tuple[str, str]] = {}
    for rnd in sorted(races["round"].unique()):
        rnd = int(rnd)
        rnd_races = races[races["round"] == rnd]
        grid = rnd_races[rnd_races["grid_position"] == 1]
        if not grid.empty:
            row = grid.iloc[0]
            poles[rnd] = (str(row["driver_key"]), str(row["team_norm"]))
            continue
        if quali.empty:
            continue
        rnd_q = quali[quali["round"] == rnd]
        if rnd_q.empty:
            continue
        q1 = rnd_q[rnd_q["position"] == 1]
        if not q1.empty:
            row = q1.iloc[0]
            team = normalize_team(str(row.get("team") or ""))
            poles[rnd] = (str(row["driver_key"]), team)
    return poles


def build_season_stats(sessions: pd.DataFrame, season: int, leaderboard: dict) -> dict:
    """Build driver/constructor season stats aligned with a leaderboard payload."""
    del leaderboard  # colors resolved from session meta / team lookup
    if sessions is None or sessions.empty:
        return {"drivers": [], "constructors": []}

    races = sessions[(sessions["year"] == season) & (sessions["session"] == "R")].copy()
    quali = sessions[(sessions["year"] == season) & (sessions["session"] == "Q")].copy()
    if races.empty:
        return {"drivers": [], "constructors": []}

    races["driver_key"] = races["driver_code"].fillna("").astype(str)
    races["team_norm"] = races["team"].fillna("").apply(normalize_team)
    if not quali.empty:
        quali = quali.copy()
        quali["driver_key"] = quali["driver_code"].fillna("").astype(str)

    poles_by_round = _pole_holders(races, quali)

    driver_meta: dict[str, dict] = {}
    for _, row in races.sort_values("round").iterrows():
        key = str(row["driver_key"])
        if not key:
            continue
        driver_meta[key] = {
            "name": str(row.get("driver_name") or key),
            "team": str(row["team_norm"] or ""),
        }

    d_wins: dict[str, int] = defaultdict(int)
    d_podiums: dict[str, int] = defaultdict(int)
    d_poles: dict[str, int] = defaultdict(int)
    d_dnfs: dict[str, int] = defaultdict(int)

    c_wins: dict[str, int] = defaultdict(int)
    c_podiums: dict[str, int] = defaultdict(int)
    c_poles: dict[str, int] = defaultdict(int)
    c_dnfs: dict[str, int] = defaultdict(int)

    for _, row in races.iterrows():
        key = str(row["driver_key"])
        team = str(row["team_norm"] or "")
        status = str(row.get("status") or "")
        if not key:
            continue

        if _is_dnf(status):
            d_dnfs[key] += 1
            if team:
                c_dnfs[team] += 1

        try:
            pos = int(row["position"])
        except (TypeError, ValueError):
            continue
        if pos <= 0:
            continue
        if pos == 1:
            d_wins[key] += 1
            if team:
                c_wins[team] += 1
        if pos <= 3:
            d_podiums[key] += 1
            if team:
                c_podiums[team] += 1

    for _, (pole_driver, pole_team) in poles_by_round.items():
        if pole_driver:
            d_poles[pole_driver] += 1
        if pole_team:
            c_poles[pole_team] += 1

    drivers_out = []
    for key, meta in driver_meta.items():
        drivers_out.append(
            {
                "id": key,
                "name": meta["name"],
                "team": meta["team"],
                "color": get_team_color(meta["team"]),
                "wins": d_wins.get(key, 0),
                "poles": d_poles.get(key, 0),
                "podiums": d_podiums.get(key, 0),
                "dnfs": d_dnfs.get(key, 0),
            }
        )

    all_teams = sorted(t for t in races["team_norm"].unique() if t)
    constructors_out = []
    for team in all_teams:
        constructors_out.append(
            {
                "name": team,
                "color": get_team_color(team),
                "wins": c_wins.get(team, 0),
                "poles": c_poles.get(team, 0),
                "podiums": c_podiums.get(team, 0),
                "dnfs": c_dnfs.get(team, 0),
            }
        )

    return {"drivers": drivers_out, "constructors": constructors_out}
