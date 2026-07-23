"""Lightweight championship results via Jolpica (Ergast successor).

Used to fill leaderboard seasons when FastF1 is rate-limited. Returns the same
row shape as ingest._session_rows for race/sprint results (no lap times).
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"


def _get(path: str, params: dict | None = None, *, retries: int = 6) -> dict:
    import time

    url = f"{JOLPICA_BASE}/{path}"
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                params=params or {},
                timeout=45,
                headers={"User-Agent": "DeltaV/1.0"},
            )
            if resp.status_code == 429:
                wait = min(60.0, 2.0 ** attempt)
                logger.warning("Jolpica 429 on %s — sleep %.1fs", path, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            wait = min(45.0, 1.5 ** attempt)
            logger.debug("Jolpica %s attempt %d failed: %s", path, attempt + 1, exc)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _result_rows(year: int, race: dict[str, Any], session: str) -> list[dict]:
    rnd = int(race.get("round", 0) or 0)
    if rnd <= 0:
        return []
    event_name = race.get("raceName") or f"Round {rnd}"
    circuit = (race.get("Circuit") or {}).get("circuitName") or ""
    location = ((race.get("Circuit") or {}).get("Location") or {}).get("locality") or ""
    country = ((race.get("Circuit") or {}).get("Location") or {}).get("country") or ""
    results = race.get("Results") or race.get("SprintResults") or []
    rows: list[dict] = []
    for r in results:
        driver = r.get("Driver") or {}
        constructor = r.get("Constructor") or {}
        try:
            position = int(r.get("position"))
        except (TypeError, ValueError):
            continue
        code = str(driver.get("code") or "").upper().strip()
        name = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
        # Pre-~2005 Ergast often omits radio tricodes; fall back to unique driverId
        # so rows don't collapse under an empty-string key during dedupe.
        if not code:
            did = str(driver.get("driverId") or "").strip()
            if did:
                code = did.upper()
            else:
                family = "".join(c for c in str(driver.get("familyName") or "").upper() if c.isalpha())
                code = (family[:3] if len(family) >= 3 else (family or "UNK"))
        team = str(constructor.get("name") or "")
        try:
            points = float(r.get("points", 0) or 0)
        except (TypeError, ValueError):
            points = 0.0
        grid = r.get("grid")
        try:
            grid_position = int(grid) if grid not in (None, "") else None
        except (TypeError, ValueError):
            grid_position = None
        rows.append(
            {
                "year": year,
                "round": rnd,
                "session": session,
                "event_name": event_name,
                "circuit": location or circuit,
                "country": country,
                "driver_number": int(driver.get("permanentNumber") or 0) or 0,
                "driver_code": code,
                "driver_name": name,
                "team": team,
                "grid_position": grid_position,
                "position": position,
                "status": str(r.get("status") or ""),
                "points": points,
                "q1": None,
                "q2": None,
                "q3": None,
                "best_lap_time": None,
                "median_lap_time": None,
                "stint_count": None,
                "compound_mix": None,
            }
        )
    return rows


def fetch_season_results(year: int, *, min_interval: float = 0.35) -> pd.DataFrame:
    """Fetch all race (+ sprint) results for a season from Jolpica."""
    import time

    rows: list[dict] = []
    try:
        schedule = _get(f"{year}.json", {"limit": 100})
        races_meta = schedule.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        rounds = sorted(int(r["round"]) for r in races_meta if r.get("round"))
        time.sleep(min_interval)
    except Exception as exc:
        logger.warning("Jolpica schedule failed for %d: %s", year, exc)
        return pd.DataFrame()

    race_events = 0
    for rnd in rounds:
        got_race = False
        try:
            data = _get(f"{year}/{rnd}/results.json", {"limit": 100})
            races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            for race in races:
                got = _result_rows(year, race, "R")
                if got:
                    race_events += 1
                    got_race = True
                rows.extend(got)
        except Exception as exc:
            logger.warning("Jolpica %d R%d race failed: %s", year, rnd, exc)
        time.sleep(min_interval)

        # Sprints only exist from 2021 onward — skip the extra call for older years.
        if year >= 2021:
            try:
                data = _get(f"{year}/{rnd}/sprint.json", {"limit": 100})
                races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                for race in races:
                    rows.extend(_result_rows(year, race, "S"))
            except Exception:
                pass
            time.sleep(min_interval)
        elif not got_race:
            time.sleep(min_interval)

    logger.info(
        "Jolpica %d: %d/%d race events, %d total result rows",
        year,
        race_events,
        len(rounds),
        len(rows),
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fill_leaderboard_seasons(years: list[int], *, min_interval: float = 0.35) -> pd.DataFrame:
    """Merge Jolpica race/sprint results into sessions.parquet for given years.

    Only replaces a season when the new pull has at least as many race rounds
    as what's already stored (avoids wiping a complete FastF1 ingest with a
    rate-limited partial pull).
    """
    from ingest import PARQUET_PATH, load_sessions
    import time

    existing = load_sessions()
    frames: list[pd.DataFrame] = []
    for year in years:
        df = fetch_season_results(year, min_interval=min_interval)
        if df.empty:
            continue
        new_rounds = int(df[df["session"] == "R"]["round"].nunique())
        if not existing.empty:
            old = existing[(existing["year"] == year) & (existing["session"] == "R")]
            old_rounds = int(old["round"].nunique()) if not old.empty else 0
            if new_rounds < old_rounds:
                logger.warning(
                    "Skipping Jolpica %d (%d rounds) — existing data has %d",
                    year,
                    new_rounds,
                    old_rounds,
                )
                continue
        frames.append(df)
        logger.info("Accepting Jolpica %d (%d race rounds)", year, new_rounds)
        time.sleep(min_interval)

    if not frames:
        return existing

    accepted_years = {int(f["year"].iloc[0]) for f in frames}
    combined = pd.concat(frames, ignore_index=True)
    if not existing.empty:
        keep = existing[
            ~((existing["year"].isin(accepted_years)) & (existing["session"].isin(["R", "S"])))
        ]
        combined = pd.concat([keep, combined], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["year", "round", "session", "driver_code"],
            keep="last",
        )
    combined.to_parquet(PARQUET_PATH, index=False)
    logger.info("Wrote %d rows to %s (Jolpica fill)", len(combined), PARQUET_PATH)
    return combined


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    fill_leaderboard_seasons(years)
