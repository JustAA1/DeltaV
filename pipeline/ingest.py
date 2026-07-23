"""FastF1 data ingestion into parquet."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from config import CACHE_DIR, CURRENT_SEASON, DATA_DIR, INGEST_SEASONS, PARQUET_PATH

logger = logging.getLogger(__name__)

SESSION_TYPES = ["FP1", "FP2", "FP3", "Q", "S", "R"]
# Historical seasons used for model features (need quali + race)
SESSION_TYPES_HISTORICAL = ["Q", "S", "R"]
# Pre-2024 seasons only needed for championship leaderboards
SESSION_TYPES_LEADERBOARD = ["R", "S"]
LEADERBOARD_ONLY_BEFORE = 2024


def _ensure_dirs() -> None:
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)


def _enable_cache() -> None:
    try:
        import fastf1

        fastf1.Cache.enable_cache(CACHE_DIR)
    except Exception as exc:
        logger.warning("Could not enable FastF1 cache: %s", exc)


def _safe_session_attr(session, attr: str, default=None):
    """Read a session attribute that may raise DataNotLoadedError."""
    try:
        return getattr(session, attr)
    except Exception as exc:
        logger.debug("Could not read session.%s: %s", attr, exc)
        return default


def _session_rows(year: int, rnd: int, session_type: str, *, results_only: bool = False) -> list[dict]:
    import fastf1

    rows: list[dict] = []
    try:
        session = fastf1.get_session(year, rnd, session_type)
        session.load(
            laps=not results_only,
            telemetry=False,
            weather=False,
            messages=False,
        )
    except Exception as exc:
        logger.debug("Skip %d R%d %s: %s", year, rnd, session_type, exc)
        return rows

    event = _safe_session_attr(session, "event")
    event_name = getattr(event, "EventName", "") if event is not None else ""
    circuit = getattr(event, "Location", "") if event is not None else ""
    country = getattr(event, "Country", "") if event is not None else ""

    results = _safe_session_attr(session, "results")
    if results is not None and len(results) > 0:
        for _, r in results.iterrows():
            pos = r.get("Position")
            if pd.isna(pos):
                continue
            try:
                position = int(pos)
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "year": year,
                    "round": rnd,
                    "session": session_type,
                    "event_name": event_name,
                    "circuit": circuit,
                    "country": country,
                    "driver_number": int(r.get("DriverNumber", 0) or 0),
                    "driver_code": str(r.get("Abbreviation", "") or ""),
                    "driver_name": str(r.get("FullName", "") or r.get("BroadcastName", "") or ""),
                    "team": str(r.get("TeamName", "") or ""),
                    "grid_position": _safe_int(r.get("GridPosition")),
                    "position": position,
                    "status": str(r.get("Status", "") or ""),
                    "points": float(r.get("Points", 0) or 0),
                    "q1": _safe_float(r.get("Q1")),
                    "q2": _safe_float(r.get("Q2")),
                    "q3": _safe_float(r.get("Q3")),
                    "best_lap_time": None,
                    "median_lap_time": None,
                    "stint_count": None,
                    "compound_mix": None,
                }
            )

    if results_only:
        return rows

    laps = _safe_session_attr(session, "laps")
    if laps is not None and len(laps) > 0:
        for driver_num, dl in laps.groupby("DriverNumber"):
            driver_num = int(driver_num)
            clean = dl[dl["PitOutTime"].isna() & dl["PitInTime"].isna()]
            if len(clean) == 0:
                clean = dl
            best = clean["LapTime"].min() if "LapTime" in clean.columns else None
            best_sec = best.total_seconds() if best is not None and pd.notna(best) else None

            median_sec = _median_green_lap(dl, clean)

            stint_count = dl["Stint"].nunique() if "Stint" in dl.columns else None
            compounds = (
                ",".join(sorted(dl["Compound"].dropna().unique().astype(str)))
                if "Compound" in dl.columns
                else None
            )

            existing = [i for i, row in enumerate(rows) if row["driver_number"] == driver_num]
            if existing:
                idx = existing[0]
                rows[idx]["best_lap_time"] = best_sec
                rows[idx]["median_lap_time"] = median_sec
                rows[idx]["stint_count"] = stint_count
                rows[idx]["compound_mix"] = compounds
            elif session_type in ("FP1", "FP2", "FP3"):
                try:
                    driver_info = session.get_driver(str(driver_num))
                except Exception:
                    driver_info = None
                rows.append(
                    {
                        "year": year,
                        "round": rnd,
                        "session": session_type,
                        "event_name": event_name,
                        "circuit": circuit,
                        "country": country,
                        "driver_number": driver_num,
                        "driver_code": _driver_field(driver_info, "Abbreviation"),
                        "driver_name": _driver_field(driver_info, "FullName"),
                        "team": _driver_field(driver_info, "TeamName"),
                        "grid_position": None,
                        "position": None,
                        "status": "",
                        "points": 0.0,
                        "q1": None,
                        "q2": None,
                        "q3": None,
                        "best_lap_time": best_sec,
                        "median_lap_time": median_sec,
                        "stint_count": stint_count,
                        "compound_mix": compounds,
                    }
                )

    return rows


def _median_green_lap(dl, clean) -> float | None:
    """Median green-flag, accurate lap time (seconds) for stint-pace estimate.

    Filters to representative racing laps: excludes pit in/out laps, non-green
    (safety car / VSC / yellow) laps, and laps FastF1 flags as inaccurate.
    Falls back progressively so we still return something usable.
    """
    if "LapTime" not in dl.columns:
        return None
    green = clean
    try:
        if "IsAccurate" in green.columns:
            acc = green[green["IsAccurate"] == True]  # noqa: E712
            if len(acc) > 0:
                green = acc
        if "TrackStatus" in green.columns:
            g = green[green["TrackStatus"].astype(str) == "1"]
            if len(g) > 0:
                green = g
    except Exception:
        pass
    times = green["LapTime"].dropna()
    if len(times) == 0:
        times = clean["LapTime"].dropna()
    if len(times) == 0:
        return None
    med = times.median()
    return med.total_seconds() if pd.notna(med) else None


def _driver_field(driver_info, field: str) -> str:
    if driver_info is None:
        return ""
    try:
        val = getattr(driver_info, field, None)
        if val is None and hasattr(driver_info, "get"):
            val = driver_info.get(field)
        return str(val or "")
    except Exception:
        return ""


def _safe_int(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _safe_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if hasattr(val, "total_seconds"):
            return val.total_seconds()
        return float(val)
    except (TypeError, ValueError):
        return None


def _completed_rounds(year: int) -> list[int]:
    """Return round numbers that have a completed race in the schedule."""
    import fastf1

    _enable_cache()
    try:
        schedule = fastf1.get_event_schedule(year)
    except Exception as exc:
        logger.warning("Could not load schedule for %d: %s", year, exc)
        return []

    now = pd.Timestamp.now(tz="UTC")
    rounds: list[int] = []
    for _, event in schedule.iterrows():
        rnd = event.get("RoundNumber")
        if pd.isna(rnd):
            continue
        rnd = int(rnd)
        event_date = event.get("EventDate")
        if event_date is not None and not pd.isna(event_date):
            ts = pd.Timestamp(event_date)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            if ts > now:
                continue
        rounds.append(rnd)
    return sorted(set(rounds))


def ingest_season(year: int, max_round: int | None = None) -> pd.DataFrame:
    """Ingest one season of session data."""
    import fastf1

    _enable_cache()
    try:
        schedule = fastf1.get_event_schedule(year)
    except Exception as exc:
        logger.warning("Could not load schedule for %d: %s", year, exc)
        return pd.DataFrame()

    if year == CURRENT_SEASON:
        rounds = _completed_rounds(year)
    else:
        rounds = [
            int(r)
            for r in schedule["RoundNumber"].dropna().astype(int).tolist()
            if int(r) > 0
        ]

    if max_round is not None:
        rounds = [r for r in rounds if r <= max_round]

    if not rounds:
        logger.warning("No rounds to ingest for %d", year)
        return pd.DataFrame()

    # Rounds that use a sprint format (have an 'S' session)
    sprint_rounds: set[int] = set()
    try:
        for _, ev in schedule.iterrows():
            fmt = str(ev.get("EventFormat", "") or "")
            rnum = ev.get("RoundNumber")
            if "sprint" in fmt.lower() and not pd.isna(rnum):
                sprint_rounds.add(int(rnum))
    except Exception:
        pass

    if year == CURRENT_SEASON:
        base_types = SESSION_TYPES
    elif year >= LEADERBOARD_ONLY_BEFORE:
        base_types = SESSION_TYPES_HISTORICAL
    else:
        # Older seasons: race + sprint only (enough for championship charts)
        base_types = SESSION_TYPES_LEADERBOARD
    all_rows: list[dict] = []
    for rnd in rounds:
        round_rows: list[dict] = []
        session_types = [s for s in base_types if s != "S" or rnd in sprint_rounds]
        results_only = year < LEADERBOARD_ONLY_BEFORE
        for ses in session_types:
            try:
                logger.info("Ingesting %d round %d %s", year, rnd, ses)
                round_rows.extend(_session_rows(year, rnd, ses, results_only=results_only))
            except Exception as exc:
                logger.warning("Failed %d R%d %s: %s", year, rnd, ses, exc)
        if round_rows:
            all_rows.extend(round_rows)
        else:
            logger.warning("No data for %d round %d", year, rnd)

    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def ingest(
    seasons: list[int] | None = None,
    current_season_only: bool = False,
    max_round_2026: int | None = None,
) -> pd.DataFrame:
    """Ingest configured seasons into parquet."""
    _ensure_dirs()
    seasons = seasons or INGEST_SEASONS

    if current_season_only:
        seasons = [CURRENT_SEASON]

    frames: list[pd.DataFrame] = []
    for year in seasons:
        max_rnd = max_round_2026 if year == CURRENT_SEASON else None
        try:
            df = ingest_season(year, max_round=max_rnd)
            if len(df) > 0:
                frames.append(df)
        except Exception as exc:
            logger.error("Season %d ingest failed: %s", year, exc)

    if not frames:
        logger.warning("No data ingested from FastF1")
        existing = load_sessions()
        if not existing.empty:
            logger.info("Keeping existing parquet with %d rows", len(existing))
            return existing
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    existing = load_sessions()
    if not existing.empty:
        combined = pd.concat([existing, combined], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["year", "round", "session", "driver_code"],
            keep="last",
        )
    combined.to_parquet(PARQUET_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(combined), PARQUET_PATH)
    return combined


def load_sessions(path: str | None = None) -> pd.DataFrame:
    """Load sessions parquet or return empty frame."""
    p = path or PARQUET_PATH
    if os.path.exists(p):
        return pd.read_parquet(p)
    return pd.DataFrame()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingest FastF1 data")
    parser.add_argument("--seasons", type=int, nargs="+", default=None)
    parser.add_argument("--current-only", action="store_true")
    parser.add_argument("--max-round", type=int, default=None, help="Max round for current season")
    args = parser.parse_args()
    ingest(seasons=args.seasons, current_season_only=args.current_only, max_round_2026=args.max_round)
