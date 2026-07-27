"""Podiumigami: first-time unordered driver trios on the podium since 1980."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from config import LEADERBOARD_SEASONS, OUTPUTS_DIR, get_team_color, normalize_team

logger = logging.getLogger(__name__)

PODIUMIGAMI_FROM_YEAR = 1980


def _driver_entry(row: pd.Series) -> dict[str, Any]:
    code = str(row.get("driver_code") or "").strip()
    name = str(row.get("driver_name") or code)
    team = normalize_team(str(row.get("team") or ""))
    try:
        from assets import image_for_driver

        image = image_for_driver(code, name)
    except Exception:
        image = None
    return {
        "position": int(row["position"]),
        "code": code,
        "name": name,
        "team": team,
        "color": get_team_color(team),
        "image": image,
    }


def _trio_key(codes: list[str]) -> str:
    return "|".join(sorted(codes))


def _drivers_from_podium(podium: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drivers in finishing order (P1 → P2 → P3) from the sample race."""
    ordered = sorted(podium, key=lambda d: int(d.get("position") or 99))
    return [
        {
            "code": d["code"],
            "name": d["name"],
            "team": d["team"],
            "color": d["color"],
            "image": d.get("image"),
            "position": int(d.get("position") or 0),
        }
        for d in ordered
    ]


def _ranked_trios(
    counter: Counter[str],
    races: list[dict],
    *,
    all_time_counts: Counter[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Rank trios by count desc, then most recent occurrence.

    Driver order for each trio comes from its most recent race (P1–P2–P3).
    ``is_podiumigami`` is always based on all-time uniqueness (once ever), not
    season-local counts.
    """
    last_seen: dict[str, tuple[int, int]] = {}
    sample: dict[str, list[dict]] = {}
    first_year: dict[str, int] = {}
    last_year: dict[str, int] = {}
    last_event: dict[str, str] = {}
    for race in races:
        key = race["key"]
        last_seen[key] = (race["year"], race["round"])
        sample[key] = race["podium"]  # chronological walk → last write = most recent
        y = race["year"]
        if key not in first_year or y < first_year[key]:
            first_year[key] = y
        # Chronological walk → last write is the most recent occurrence
        last_year[key] = y
        last_event[key] = str(race.get("event_name") or "")

    ranked = sorted(
        counter.items(),
        key=lambda kv: (-kv[1], -last_seen.get(kv[0], (0, 0))[0], -last_seen.get(kv[0], (0, 0))[1]),
    )
    if limit is not None:
        ranked = ranked[:limit]

    lifetime = all_time_counts if all_time_counts is not None else counter

    out: list[dict[str, Any]] = []
    for key, count in ranked:
        podium = sample.get(key, [])
        lifetime_count = int(lifetime.get(key, count))
        out.append(
            {
                "key": key,
                "count": count,
                "is_podiumigami": lifetime_count == 1,
                "podium": podium,
                "drivers": _drivers_from_podium(podium),
                "first_year": first_year.get(key),
                "last_year": last_year.get(key),
                "last_event_name": last_event.get(key) or None,
            }
        )
    return out


def _country_from_group(grp: pd.DataFrame) -> str:
    if "country" not in grp.columns or not grp["country"].notna().any():
        return ""
    return str(grp["country"].dropna().iloc[0]).strip()


def build_podiumigami(sessions: pd.DataFrame | None = None) -> dict[str, Any]:
    """Build full podiumigami dataset from race sessions."""
    if sessions is None:
        from ingest import load_sessions

        sessions = load_sessions()

    if sessions is None or sessions.empty:
        return {"from_year": PODIUMIGAMI_FROM_YEAR, "hero": None, "all_time": {}, "by_season": {}}

    races_df = sessions[
        (sessions["year"].isin(LEADERBOARD_SEASONS))
        & (sessions["session"] == "R")
        & (sessions["position"].isin([1, 2, 3]))
    ].copy()
    races_df["position"] = pd.to_numeric(races_df["position"], errors="coerce")
    races_df = races_df[races_df["position"].notna()]

    race_groups: list[tuple[int, int, str, str, pd.DataFrame]] = []
    for (year, rnd), grp in races_df.groupby(["year", "round"], sort=True):
        if len(grp) < 3:
            continue
        event = (
            str(grp["event_name"].dropna().iloc[0])
            if grp["event_name"].notna().any()
            else f"Round {int(rnd)}"
        )
        country = _country_from_group(grp)
        race_groups.append((int(year), int(rnd), event, country, grp.sort_values("position")))

    trio_counts: Counter[str] = Counter()
    decade_races: dict[str, int] = defaultdict(int)
    decade_unique: dict[str, set[str]] = defaultdict(set)
    decade_trio: dict[str, Counter[str]] = defaultdict(Counter)
    decade_race_lists: dict[str, list[dict]] = defaultdict(list)
    season_races: dict[int, list[dict]] = defaultdict(list)
    season_trio: dict[int, Counter[str]] = defaultdict(Counter)
    season_podiumigamis: dict[int, int] = defaultdict(int)

    all_races: list[dict] = []
    hero: dict | None = None
    # Most recent prior race for each trio key (year, round, event_name)
    prior_race: dict[str, tuple[int, int, str]] = {}

    for year, rnd, event, country, grp in race_groups:
        podium = [_driver_entry(row) for _, row in grp.iterrows()]
        codes = [d["code"] for d in podium]
        key = _trio_key(codes)

        occurrence = trio_counts[key] + 1
        trio_counts[key] += 1
        is_podiumigami = occurrence == 1
        prev = prior_race.get(key)

        decade = f"{(year // 10) * 10}s"
        decade_races[decade] += 1
        decade_unique[decade].add(key)
        decade_trio[decade][key] += 1
        season_trio[year][key] += 1
        if is_podiumigami:
            season_podiumigamis[year] += 1

        race_rec = {
            "year": year,
            "round": rnd,
            "event_name": event,
            "country": country,
            "podium": podium,
            "key": key,
            "is_podiumigami": is_podiumigami,
            "occurrence": occurrence,
            "occurrence_in_year": season_trio[year][key],
            "trio_count": 0,  # filled after final counts known
            "last_occurred_year": prev[0] if prev else None,
            "last_occurred_event": prev[2] if prev else None,
        }
        all_races.append(race_rec)
        season_races[year].append(race_rec)
        decade_race_lists[decade].append(race_rec)
        prior_race[key] = (year, rnd, event)
        if is_podiumigami:
            hero = race_rec

    # Attach final all-time trio counts for list badges
    for race in all_races:
        race["trio_count"] = int(trio_counts[race["key"]])

    all_trios_ranked = _ranked_trios(trio_counts, all_races, all_time_counts=trio_counts)
    top_trios = all_trios_ranked[:3]

    decade_breakdown = []
    for decade in sorted(decade_races.keys()):
        decade_ranked = _ranked_trios(
            decade_trio[decade],
            decade_race_lists[decade],
            all_time_counts=trio_counts,
        )
        decade_breakdown.append(
            {
                "decade": decade,
                "races": decade_races[decade],
                "podiumigamis": len(decade_unique[decade]),
                "top_trios": decade_ranked[:3],
                "all_trios_ranked": decade_ranked,
            }
        )

    all_time = {
        "total_races": len(all_races),
        "podiumigamis": len(trio_counts),
        "one_time_only": sum(1 for c in trio_counts.values() if c == 1),
        "top_trios": top_trios,
        "all_trios_ranked": all_trios_ranked,
        "decade_breakdown": decade_breakdown,
        "recent_races": list(reversed(all_races[-30:])),
    }

    by_season: dict[str, dict] = {}
    for year in sorted(season_races.keys()):
        year_races = season_races[year]
        year_counter = season_trio[year]
        year_ranked = _ranked_trios(
            year_counter,
            year_races,
            all_time_counts=trio_counts,
        )
        by_season[str(year)] = {
            "year": year,
            "total_races": len(year_races),
            "podiumigamis": season_podiumigamis[year],
            "top_trios": year_ranked[:3],
            "all_trios_ranked": year_ranked,
            "races": list(reversed(year_races)),
            # Most recent podiumigami in this season (races chronological; last True wins)
            "hero": next(
                (r for r in reversed(year_races) if r["is_podiumigami"]),
                None,
            ),
        }

    return {
        "from_year": PODIUMIGAMI_FROM_YEAR,
        "hero": hero,
        "all_time": all_time,
        "by_season": by_season,
    }


def write_podiumigami(sessions: pd.DataFrame | None = None) -> dict[str, Any]:
    data = build_podiumigami(sessions)
    path = os.path.join(OUTPUTS_DIR, "podiums.json")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(
        "Podiumigami: %d races, %d podiumigamis, hero %s",
        data.get("all_time", {}).get("total_races", 0),
        data.get("all_time", {}).get("podiumigamis", 0),
        f"{data['hero']['year']} R{data['hero']['round']}" if data.get("hero") else "none",
    )
    return data


def slice_podiumigami(data: dict[str, Any], season: int | None = None) -> dict[str, Any]:
    """Return API payload, optionally scoped to one season."""
    if season is None:
        return data
    key = str(season)
    if key not in data.get("by_season", {}):
        raise ValueError(f"No podiumigami data for season {season}")
    return {
        "from_year": data["from_year"],
        "hero": data.get("hero"),
        "season": data["by_season"][key],
        "all_time": data.get("all_time"),
    }
