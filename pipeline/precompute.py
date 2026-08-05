"""CLI entrypoint: ingest -> leaderboards -> replays -> sync (incl. Merc What If)."""

from __future__ import annotations

import argparse
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _has_real_data() -> bool:
    from ingest import load_sessions

    sessions = load_sessions()
    return not sessions.empty


def _step(n: int, total: int, label: str) -> None:
    logger.info("─── [%d/%d] %s ───", n, total, label)


def _finish_outputs() -> None:
    """Ensure podiumigami + site/public/api are up to date after any output write."""
    try:
        from ingest import load_sessions
        from podiumigami import write_podiumigami

        sessions = load_sessions()
        if not sessions.empty:
            write_podiumigami(sessions)
        else:
            logger.warning("No sessions for podiumigami; skipping")
    except Exception as exc:
        logger.warning("Podiumigami refresh failed: %s", exc)

    from sync_site_api import sync_site_api

    sync_site_api()


def main() -> int:
    parser = argparse.ArgumentParser(description="DeltaV precompute pipeline")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip FastF1 ingest")
    parser.add_argument("--skip-assets", action="store_true", help="Skip headshot/logo refresh")
    parser.add_argument("--skip-replays", action="store_true", help="Skip race-replay telemetry build")
    parser.add_argument("--current-only", action="store_true", help="Ingest current season only")
    parser.add_argument("--max-round", type=int, default=None, help="Max round for 2026 ingest")
    args = parser.parse_args()
    started = time.monotonic()

    total_steps = 5
    step = 0

    step += 1
    _step(step, total_steps, "Driver assets (headshots / logos)")
    if args.skip_assets:
        logger.info("Skipped (--skip-assets)")
    else:
        from assets import build_drivers_json

        build_drivers_json(use_openf1=True)

    step += 1
    _step(step, total_steps, "Ingest race data")
    if not args.skip_ingest:
        from ingest import ingest, load_sessions

        try:
            df = ingest(current_season_only=args.current_only, max_round_2026=args.max_round)
            if df.empty and not _has_real_data():
                logger.error("Ingest returned no data and no cached parquet exists")
                return 1
        except Exception as exc:
            logger.error("Ingest failed: %s", exc)
            if not _has_real_data():
                return 1
            logger.info("Continuing with existing parquet data")
    else:
        from ingest import load_sessions

        logger.info("Skipped (--skip-ingest)")
        if load_sessions().empty:
            logger.error("No parquet data — run ingest first")
            return 1

    step += 1
    _step(step, total_steps, "Leaderboards (+ Formula 1.5 + Reversed)")
    from ingest import load_sessions
    from leaderboard import write_leaderboards

    sessions = load_sessions()
    if sessions.empty:
        logger.error("Cannot build leaderboards without session data")
        return 1
    try:
        write_leaderboards(sessions)
    except Exception as exc:
        logger.error("Leaderboard build failed: %s", exc)
        return 1

    step += 1
    _step(step, total_steps, "Race replays (telemetry)")
    if args.skip_replays:
        logger.info("Skipped (--skip-replays)")
    else:
        try:
            from config import CURRENT_SEASON
            from replays import build_replays

            # Completed races only when --max-round is set; otherwise try the calendar.
            replay_rounds = None
            if args.max_round is not None:
                replay_rounds = list(range(1, args.max_round + 1))
            build_replays(CURRENT_SEASON, replay_rounds, skip_existing=True)
        except Exception as exc:
            logger.warning("Replay build failed (continuing): %s", exc)

    step += 1
    _step(step, total_steps, "Sync site/public/api (+ Mercedes 2026 What If)")
    _finish_outputs()

    elapsed = time.monotonic() - started
    logger.info("Precompute pipeline complete in %.1fs", elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
