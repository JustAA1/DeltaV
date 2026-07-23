"""Race points schedules and drivers' championship counting rules."""

from __future__ import annotations

from config import (
    DRIVERS_BEST_N_RESULTS,
    DRIVERS_SPLIT_BEST_N,
    LEADERBOARD_SEASONS,
    POINTS_SYSTEM,
    SPRINT_POINTS_SYSTEM,
)


def race_points_schedule(year: int) -> list[float]:
    if year >= 2010:
        return list(POINTS_SYSTEM)
    if year >= 2003:
        return [10, 8, 6, 5, 4, 3, 2, 1]
    if year >= 1991:
        return [10, 6, 4, 3, 2, 1]
    return [9, 6, 4, 3, 2, 1]


def sprint_points_schedule(year: int) -> list[float]:
    if year >= 2021:
        return list(SPRINT_POINTS_SYSTEM)
    return []


def race_points_system_label(year: int) -> str:
    if year >= 2010:
        return "25-point system"
    if year >= 2003:
        return "Top 8 scored"
    if year >= 1991:
        return "Top 6 scored"
    return "9-6-4-3-2-1"


def race_signature_key(year: int) -> str:
    return ",".join(str(x) for x in race_points_schedule(year))


def has_drivers_counting_rules(year: int) -> bool:
    return year in DRIVERS_BEST_N_RESULTS or year in DRIVERS_SPLIT_BEST_N


def counting_season_for_points_what_if(season: int, points_from_year: int) -> int:
    """Pick which era's dropped-scores rules apply when replaying a season."""
    if has_drivers_counting_rules(season):
        return season
    if has_drivers_counting_rules(points_from_year):
        return points_from_year
    return season


def championship_counting_key(year: int) -> str:
    split = DRIVERS_SPLIT_BEST_N.get(year)
    if split:
        return f"split:{split[0]}:{split[1]}:{split[2]}"
    best_n = DRIVERS_BEST_N_RESULTS.get(year)
    if best_n:
        return f"best:{best_n}"
    return "all"


def championship_counting_label(year: int) -> str | None:
    split = DRIVERS_SPLIT_BEST_N.get(year)
    if split:
        first_size, best_first, best_second = split
        return (
            f"Best {best_first} from first {first_size}, "
            f"best {best_second} from the rest"
        )
    best_n = DRIVERS_BEST_N_RESULTS.get(year)
    if best_n:
        return f"Best {best_n} races counted"
    return None


def get_points_system_changes() -> dict:
    changes: dict[str, str] = {}
    season_changes: dict[str, str] = {}
    systems: dict[str, str] = {}
    seasons = sorted(LEADERBOARD_SEASONS)
    if not seasons:
        return {"changes": changes, "seasonChanges": season_changes, "systems": systems}
    prev_race_key: str | None = None
    prev_counting_key: str | None = None
    for year in seasons:
        year_str = str(year)
        race_key = race_signature_key(year)
        systems[year_str] = race_key

        if prev_race_key is None or race_key != prev_race_key:
            changes[year_str] = race_points_system_label(year)

        counting_key = championship_counting_key(year)
        if prev_counting_key is None or counting_key != prev_counting_key:
            counting_label = championship_counting_label(year)
            if counting_label:
                season_changes[year_str] = counting_label
            elif year_str in changes:
                season_changes[year_str] = changes[year_str]
        elif year_str in changes:
            season_changes[year_str] = changes[year_str]

        prev_race_key = race_key
        prev_counting_key = counting_key
    return {"changes": changes, "seasonChanges": season_changes, "systems": systems}
