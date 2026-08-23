"""What-if championship scenarios: remove a driver or team and shift the field."""

from __future__ import annotations

import json
import logging
import os
import unicodedata
from typing import Any

import pandas as pd

from leaderboard import build_leaderboard_from_sessions
from config import (
    CURRENT_SEASON,
    FORMULA15_NOTES,
    FORMULA15_START,
    FORMULA15_TEAMS,
    LEADERBOARD_SEASONS,
    OUTPUTS_DIR,
    get_team_color,
    normalize_team,
)
from points_rules import (
    counting_season_for_points_what_if,
    get_points_system_changes,
    race_points_schedule,
    sprint_points_schedule,
)

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def _race_points_schedule(year: int) -> list[float]:
    return race_points_schedule(year)


def _sprint_points_schedule(year: int) -> list[float]:
    return sprint_points_schedule(year)


def _points_at(schedule: list[float], position: int, multiplier: float = 1.0) -> float:
    if position <= 0:
        return 0.0
    idx = position - 1
    if idx >= len(schedule):
        return 0.0
    return round(schedule[idx] * multiplier, 1)


def _round_pts(value: float) -> float:
    return round(float(value), 1)


def _session_multiplier(group: pd.DataFrame, schedule: list[float]) -> float:
    p1 = group[group["position"] == 1]
    if p1.empty or not schedule:
        return 1.0
    actual = float(p1["points"].iloc[0])
    base = schedule[0]
    if base <= 0:
        return 1.0
    ratio = actual / base
    if abs(ratio - 0.5) < 0.06:
        return 0.5
    if abs(ratio - 2.0) < 0.06:
        return 2.0
    if 0.9 <= ratio <= 1.1:
        return 1.0
    return ratio


def _resolve_driver(season_df: pd.DataFrame, identifier: str) -> tuple[str, str] | None:
    target = _norm(identifier)
    if not target:
        return None
    seen: set[str] = set()
    exact: list[tuple[str, str]] = []
    partial: list[tuple[str, str]] = []
    for _, row in season_df.sort_values("round").iterrows():
        code = str(row.get("driver_code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        name = str(row.get("driver_name") or code)
        code_n = _norm(code)
        name_n = _norm(name)
        if code_n == target or name_n == target:
            exact.append((code, name))
        elif target in name_n or name_n in target:
            partial.append((code, name))
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return exact[0]
    if len(partial) == 1:
        return partial[0]
    return None


def _resolve_team(season_df: pd.DataFrame, identifier: str) -> str | None:
    target_norm = _norm(identifier)
    if not target_norm:
        return None
    teams = sorted(t for t in season_df["team_norm"].unique() if t)
    canonical = normalize_team(identifier)
    if canonical in teams:
        return canonical
    exact = [team for team in teams if _norm(team) == target_norm]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return exact[0]
    partial = [
        team
        for team in teams
        if target_norm in _norm(team) or _norm(team) in target_norm
    ]
    if len(partial) == 1:
        return partial[0]
    return None


def _removal_mask_df(df: pd.DataFrame, remove_type: str, remove_meta: dict[str, Any]) -> pd.Series:
    if remove_type == "driver":
        return df["driver_code"].astype(str) == str(remove_meta["id"])
    team_norm = df["team"].fillna("").apply(normalize_team)
    return team_norm == str(remove_meta["name"])


def _removal_mask(season_df: pd.DataFrame, remove_type: str, identifier: str) -> tuple[pd.Series, dict[str, Any]]:
    if remove_type == "driver":
        resolved = _resolve_driver(season_df, identifier)
        if not resolved:
            raise ValueError(f"Driver not found for season: {identifier}")
        code, display_name = resolved
        mask = season_df["driver_code"].astype(str) == code
        meta = {"type": "driver", "id": code, "name": display_name}
        return mask, meta

    if remove_type == "team":
        team = _resolve_team(season_df, identifier)
        if not team:
            raise ValueError(f"Team not found for season: {identifier}")
        mask = season_df["team_norm"] == team
        meta = {"type": "team", "name": team}
        return mask, meta

    raise ValueError(f"Invalid remove type: {remove_type}")


def _shift_grid_positions(remaining: pd.DataFrame) -> pd.DataFrame:
    """Re-assign grid slots after removals so pole credit follows the remaining field."""
    if remaining.empty or "grid_position" not in remaining.columns:
        return remaining
    gp = pd.to_numeric(remaining["grid_position"], errors="coerce")
    order = remaining.assign(_gp=gp.fillna(remaining["position"])).sort_values(
        ["_gp", "position"],
        kind="mergesort",
    )
    remaining = remaining.copy()
    remaining.loc[order.index, "grid_position"] = list(range(1, len(order) + 1))
    return remaining


def _shift_positions_only(remaining: pd.DataFrame) -> pd.DataFrame:
    """Renumber finishing positions without changing points (qualifying)."""
    if remaining.empty:
        return remaining
    remaining = remaining.sort_values("position", kind="mergesort").copy()
    remaining["position"] = list(range(1, len(remaining) + 1))
    return remaining


def _shift_sessions(season_df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    year = int(season_df["year"].iloc[0])
    parts: list[pd.DataFrame] = []

    for (_, _), grp in season_df.groupby(["round", "session"], sort=True):
        grp = grp.copy()
        remove = mask.loc[grp.index]
        remaining = grp[~remove].copy()
        if remaining.empty:
            continue

        session_type = str(remaining["session"].iloc[0])
        schedule = (
            _sprint_points_schedule(year)
            if session_type == "S"
            else _race_points_schedule(year)
        )
        if not schedule:
            schedule = _race_points_schedule(year)

        multiplier = _session_multiplier(grp, schedule)
        if session_type == "R":
            remaining = _shift_grid_positions(remaining)
        remaining = remaining.sort_values("position", kind="mergesort")
        remaining["position"] = list(range(1, len(remaining) + 1))
        remaining["points"] = [
            _points_at(schedule, int(pos), multiplier) for pos in remaining["position"]
        ]
        remaining["points"] = remaining["points"].apply(_round_pts)
        parts.append(remaining)

    if not parts:
        return pd.DataFrame(columns=season_df.columns)
    return pd.concat(parts, ignore_index=True)


def _shift_quali_sessions(quali_df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, grp in quali_df.groupby("round", sort=True):
        grp = grp.copy()
        remove = mask.loc[grp.index]
        remaining = grp[~remove].copy()
        if remaining.empty:
            continue
        parts.append(_shift_positions_only(remaining))
    if not parts:
        return pd.DataFrame(columns=quali_df.columns)
    return pd.concat(parts, ignore_index=True)


def _format_names_list(names: list[str]) -> str:
    names = [n for n in names if n]
    if not names:
        return "they"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _clause_text(remove_metas: list[dict[str, Any]], season: int) -> str:
    names = [str(m.get("name") or m.get("id") or "") for m in remove_metas]
    names = [n for n in names if n]
    return f"{_format_names_list(names)} didn't race in {season}"


def _removal_masks(
    season_df: pd.DataFrame, remove_type: str, identifiers: list[str]
) -> tuple[pd.Series, list[dict[str, Any]]]:
    if not identifiers:
        raise ValueError("At least one removal target is required")

    combined = pd.Series(False, index=season_df.index)
    metas: list[dict[str, Any]] = []
    for identifier in identifiers:
        mask, meta = _removal_mask(season_df, remove_type, identifier)
        combined |= mask
        metas.append(meta)

    if not combined.any():
        raise ValueError("Removal targets did not match any results")
    return combined, metas


def _combined_removal_mask_df(
    df: pd.DataFrame, remove_metas: list[dict[str, Any]]
) -> pd.Series:
    combined = pd.Series(False, index=df.index)
    for meta in remove_metas:
        combined |= _removal_mask_df(df, meta["type"], meta)
    return combined


def _color_for_remove_meta(season_df: pd.DataFrame, meta: dict[str, Any]) -> str:
    if meta["type"] == "team":
        return get_team_color(str(meta.get("name") or ""))
    code = str(meta.get("id") or "")
    driver_rows = season_df[season_df["driver_code"].astype(str) == code]
    team_name = str(driver_rows.iloc[-1]["team_norm"]) if not driver_rows.empty else ""
    return get_team_color(team_name)


def _enrich_remove_metas(season_df: pd.DataFrame, remove_metas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for meta in remove_metas:
        item = dict(meta)
        item["color"] = _color_for_remove_meta(season_df, meta)
        enriched.append(item)
    return enriched


def get_what_if_options(season: int, sessions: pd.DataFrame | None = None) -> dict[str, Any]:
    if season not in LEADERBOARD_SEASONS:
        raise ValueError(f"Season {season} is not available")

    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()

    leaderboard = build_leaderboard_from_sessions(sessions, season)
    drivers = [
        {
            "id": str(d.get("code") or ""),
            "name": str(d.get("name") or d.get("code") or ""),
            "team": str(d.get("team") or ""),
            "color": str(d.get("color") or get_team_color(str(d.get("team") or ""))),
        }
        for d in leaderboard.get("drivers", [])
        if d.get("code")
    ]
    teams = [
        {
            "name": str(t.get("name") or ""),
            "color": str(t.get("color") or get_team_color(str(t.get("name") or ""))),
        }
        for t in leaderboard.get("constructors", [])
        if t.get("name")
    ]
    return {
        "season": season,
        "drivers": drivers,
        "teams": teams,
    }


def compute_what_if(
    season: int,
    remove_type: str,
    identifiers: list[str] | str,
    championship: str = "drivers",
    sessions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if season not in LEADERBOARD_SEASONS:
        raise ValueError(f"Season {season} is not available")
    if championship not in ("drivers", "constructors"):
        raise ValueError("championship must be drivers or constructors")

    id_list = [identifiers] if isinstance(identifiers, str) else list(identifiers)
    if not id_list:
        raise ValueError("At least one removal target is required")

    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()

    season_df = sessions[
        (sessions["year"] == season) & (sessions["session"].isin(["R", "S"]))
    ].copy()
    if season_df.empty:
        raise ValueError(f"No session data for season {season}")

    season_df["team_norm"] = season_df["team"].fillna("").apply(normalize_team)
    mask, remove_metas = _removal_masks(season_df, remove_type, id_list)

    shifted = _shift_sessions(season_df, mask)

    quali_df = sessions[
        (sessions["year"] == season) & (sessions["session"] == "Q")
    ].copy()
    quali_shifted = pd.DataFrame()
    if not quali_df.empty:
        quali_df["team_norm"] = quali_df["team"].fillna("").apply(normalize_team)
        quali_mask = _combined_removal_mask_df(quali_df, remove_metas)
        quali_shifted = _shift_quali_sessions(quali_df, quali_mask)

    other = sessions[
        ~(
            (sessions["year"] == season)
            & (sessions["session"].isin(["R", "S", "Q"]))
        )
    ]
    frames = [other, shifted]
    if not quali_shifted.empty:
        frames.append(quali_shifted)
    combined = pd.concat(frames, ignore_index=True)

    leaderboard = build_leaderboard_from_sessions(combined, season)
    remove_metas = _enrich_remove_metas(season_df, remove_metas)
    primary = remove_metas[0]
    accent_color = str(primary.get("color") or "")
    leaderboard["what_if"] = {
        "kind": "remove",
        "clause": _clause_text(remove_metas, season),
        "season": season,
        "removes": remove_metas,
        "remove": primary,
        "championship": championship,
        "color": accent_color,
    }
    return leaderboard


def compute_formula15(
    season: int,
    sessions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Rescored midfield championship with the big 4 teams removed."""
    if season < FORMULA15_START or season > CURRENT_SEASON:
        raise ValueError(f"Formula 1.5 is not available for season {season}")
    leaderboard = compute_what_if(
        season=season,
        remove_type="team",
        identifiers=list(FORMULA15_TEAMS),
        championship="drivers",
        sessions=sessions,
    )
    leaderboard.pop("what_if", None)
    extra = FORMULA15_NOTES.get(season) or []
    if extra:
        notes = list(leaderboard.get("notes") or [])
        notes.extend(extra)
        leaderboard["notes"] = notes
    return leaderboard


def build_formula15_leaderboards(
    sessions: pd.DataFrame | None = None,
    *,
    existing_path: str | None = None,
) -> dict[str, Any]:
    """Build Formula 1.5 standings; freeze 2021–(current-1), always refresh current season."""
    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()

    path = existing_path or os.path.join(OUTPUTS_DIR, "formula15.json")
    seasons_out: dict[str, Any] = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                prior = json.load(f)
            seasons_out = dict(prior.get("seasons") or {})
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load existing Formula 1.5 file: %s", exc)

    for year in range(FORMULA15_START, CURRENT_SEASON + 1):
        key = str(year)
        if year < CURRENT_SEASON and key in seasons_out and seasons_out[key].get("drivers"):
            logger.info("Formula 1.5 %d: kept frozen standings", year)
            continue
        try:
            lb = compute_formula15(year, sessions=sessions)
        except ValueError as exc:
            logger.warning("Formula 1.5 %d skipped: %s", year, exc)
            continue
        if not lb.get("drivers"):
            logger.warning("No Formula 1.5 data for %d", year)
            continue
        seasons_out[key] = lb
        logger.info(
            "Formula 1.5 %d: %d drivers, %d stages",
            year,
            len(lb["drivers"]),
            len(lb.get("stages") or []),
        )

    return {"seasons": seasons_out}


def write_formula15_leaderboards(
    sessions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Compute and write formula15.json under OUTPUTS_DIR."""
    payload = build_formula15_leaderboards(sessions)
    path = os.path.join(OUTPUTS_DIR, "formula15.json")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Wrote Formula 1.5 leaderboards → %s", path)
    return payload


def _is_dnf_row(status: object) -> bool:
    from season_stats import _is_dnf

    return _is_dnf(str(status or ""))


def _reverse_race_sessions(season_df: pd.DataFrame) -> pd.DataFrame:
    """Reverse classified R/S finishers and rescore; DNFs keep 0 points / no place."""
    year = int(season_df["year"].iloc[0])
    parts: list[pd.DataFrame] = []

    for (_, _), grp in season_df.groupby(["round", "session"], sort=True):
        grp = grp.copy()
        session_type = str(grp["session"].iloc[0])
        schedule = (
            _sprint_points_schedule(year)
            if session_type == "S"
            else _race_points_schedule(year)
        )
        if not schedule:
            schedule = _race_points_schedule(year)

        multiplier = _session_multiplier(grp, schedule)
        dnf_mask = grp["status"].map(_is_dnf_row)
        classified = grp[~dnf_mask].sort_values("position", kind="mergesort").copy()
        dnfs = grp[dnf_mask].copy()

        if not classified.empty:
            n = len(classified)
            # Best original finish → last reversed place; last classified → P1.
            classified["position"] = list(range(n, 0, -1))
            classified["points"] = [
                _points_at(schedule, int(pos), multiplier) for pos in classified["position"]
            ]
            classified["points"] = classified["points"].apply(_round_pts)
            parts.append(classified)

        if not dnfs.empty:
            dnfs["points"] = 0.0
            dnfs["position"] = pd.NA
            parts.append(dnfs)

    if not parts:
        return pd.DataFrame(columns=season_df.columns)
    return pd.concat(parts, ignore_index=True)


def compute_reversed(
    season: int,
    sessions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Championship with classified finishing order reversed (DNFs excluded from the flip)."""
    if season not in LEADERBOARD_SEASONS:
        raise ValueError(f"Season {season} is not available")

    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()

    season_rs = sessions[
        (sessions["year"] == season) & (sessions["session"].isin(["R", "S"]))
    ].copy()
    if season_rs.empty:
        raise ValueError(f"No session data for season {season}")

    reversed_rs = _reverse_race_sessions(season_rs)
    other = sessions[
        ~((sessions["year"] == season) & (sessions["session"].isin(["R", "S"])))
    ]
    combined = pd.concat([other, reversed_rs], ignore_index=True)

    leaderboard = build_leaderboard_from_sessions(combined, season)
    note = (
        "Finishing order reversed among classified drivers (last → first). "
        "DNFs are excluded from the reverse and score 0 points."
    )
    notes = list(leaderboard.get("notes") or [])
    notes.insert(0, note)
    leaderboard["notes"] = notes
    return leaderboard


def build_reversed_leaderboards(
    sessions: pd.DataFrame | None = None,
    *,
    existing_path: str | None = None,
) -> dict[str, Any]:
    """Build reversed standings; freeze completed seasons, refresh current."""
    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()

    path = existing_path or os.path.join(OUTPUTS_DIR, "reversed.json")
    seasons_out: dict[str, Any] = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                prior = json.load(f)
            seasons_out = dict(prior.get("seasons") or {})
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load existing reversed file: %s", exc)

    years = sorted({int(y) for y in sessions["year"].unique() if int(y) in LEADERBOARD_SEASONS})
    for year in years:
        key = str(year)
        if year < CURRENT_SEASON and key in seasons_out and seasons_out[key].get("drivers"):
            logger.info("Reversed %d: kept frozen standings", year)
            continue
        try:
            lb = compute_reversed(year, sessions=sessions)
        except ValueError as exc:
            logger.warning("Reversed %d skipped: %s", year, exc)
            continue
        if not lb.get("drivers"):
            logger.warning("No reversed data for %d", year)
            continue
        seasons_out[key] = lb
        logger.info(
            "Reversed %d: %d drivers, %d stages",
            year,
            len(lb["drivers"]),
            len(lb.get("stages") or []),
        )

    return {"seasons": seasons_out}


def write_reversed_leaderboards(
    sessions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Compute and write reversed.json under OUTPUTS_DIR."""
    payload = build_reversed_leaderboards(sessions)
    path = os.path.join(OUTPUTS_DIR, "reversed.json")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Wrote reversed leaderboards → %s", path)
    return payload


def constructor_champion_from_leaderboard(season_lb: dict[str, Any]) -> dict[str, str]:
    constructors = season_lb.get("constructors") or []
    for team in constructors:
        if not team.get("disqualified"):
            name = str(team.get("name") or "")
            return {
                "name": name,
                "color": str(team.get("color") or get_team_color(name)),
            }
    if constructors:
        team = constructors[0]
        name = str(team.get("name") or "")
        return {
            "name": name,
            "color": str(team.get("color") or get_team_color(name)),
        }
    return {"name": "", "color": "#888888"}


def get_constructor_champions(precomputed: dict[str, Any] | None = None) -> dict[str, Any]:
    if precomputed is None:
        import json
        import os

        from config import OUTPUTS_DIR

        path = os.path.join(OUTPUTS_DIR, "leaderboard.json")
        with open(path, encoding="utf-8") as f:
            precomputed = json.load(f)

    champions: dict[str, dict[str, str]] = {}
    for year_str, season_lb in (precomputed.get("seasons") or {}).items():
        champ = constructor_champion_from_leaderboard(season_lb)
        if champ["name"]:
            champions[str(year_str)] = champ
    return {"champions": champions}


def _reapply_points_system_on_sessions(
    sessions: pd.DataFrame,
    season: int,
    points_from_year: int,
) -> pd.DataFrame:
    sessions = sessions.copy()
    mask = (sessions["year"] == season) & (sessions["session"].isin(["R", "S"]))
    if not mask.any():
        return sessions

    native_race = _race_points_schedule(season)
    native_sprint = _sprint_points_schedule(season)
    foreign_race = _race_points_schedule(points_from_year)
    foreign_sprint = _sprint_points_schedule(points_from_year)

    for _, grp in sessions.loc[mask].groupby(["round", "session"], sort=True):
        grp = grp.copy()
        session_type = str(grp["session"].iloc[0])
        if session_type == "S":
            if not foreign_sprint:
                sessions.loc[grp.index, "points"] = 0.0
                continue
            native_sched = native_sprint if native_sprint else native_race
            foreign_sched = foreign_sprint
        else:
            native_sched = native_race
            foreign_sched = foreign_race

        multiplier = _session_multiplier(grp, native_sched)
        grp = grp.sort_values("position", kind="mergesort")
        new_points = [
            _points_at(foreign_sched, int(pos), multiplier) for pos in grp["position"]
        ]
        sessions.loc[grp.index, "points"] = [_round_pts(p) for p in new_points]

    return sessions


def compute_points_system_what_if(
    season: int,
    points_from_year: int,
    championship: str = "drivers",
    sessions: pd.DataFrame | None = None,
    precomputed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if season not in LEADERBOARD_SEASONS:
        raise ValueError(f"Season {season} is not available")
    if points_from_year not in LEADERBOARD_SEASONS:
        raise ValueError(f"Points season {points_from_year} is not available")
    if championship not in ("drivers", "constructors"):
        raise ValueError("championship must be drivers or constructors")

    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()

    modified = _reapply_points_system_on_sessions(sessions, season, points_from_year)
    counting_season = counting_season_for_points_what_if(season, points_from_year)
    leaderboard = build_leaderboard_from_sessions(
        modified,
        season,
        counting_season=counting_season,
        race_points_from_year=points_from_year,
    )

    if precomputed is None:
        import json
        import os

        from config import OUTPUTS_DIR

        path = os.path.join(OUTPUTS_DIR, "leaderboard.json")
        with open(path, encoding="utf-8") as f:
            precomputed = json.load(f)

    season_lb = (precomputed.get("seasons") or {}).get(str(season), {})
    from_lb = (precomputed.get("seasons") or {}).get(str(points_from_year), {})
    season_champ = constructor_champion_from_leaderboard(season_lb)
    from_champ = constructor_champion_from_leaderboard(from_lb)

    clause = f"{season} had the points system from {points_from_year}"
    leaderboard["what_if"] = {
        "kind": "points",
        "clause": clause,
        "season": season,
        "points_from": points_from_year,
        "season_color": season_champ["color"],
        "points_from_color": from_champ["color"],
        "championship": championship,
        "color": season_champ["color"],
    }
    return leaderboard
