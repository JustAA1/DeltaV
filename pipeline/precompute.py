"""CLI entrypoint: ingest -> features -> model -> backtest -> sync (incl. Merc What If)."""

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


def _finish_outputs(*, mock: bool = False) -> None:
    """Ensure podiumigami + site/public/api are up to date after any output write."""
    try:
        from ingest import load_sessions
        from podiumigami import write_podiumigami

        sessions = load_sessions()
        if not sessions.empty:
            write_podiumigami(sessions)
        elif mock:
            logger.warning("No sessions for podiumigami; skipping")
    except Exception as exc:
        logger.warning("Podiumigami refresh failed: %s", exc)

    from sync_site_api import sync_site_api

    sync_site_api()


def main() -> int:
    parser = argparse.ArgumentParser(description="DeltaV precompute pipeline")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip FastF1 ingest")
    parser.add_argument("--skip-assets", action="store_true", help="Skip headshot/logo refresh")
    parser.add_argument("--mock", action="store_true", help="Generate mock outputs only")
    parser.add_argument("--current-only", action="store_true", help="Ingest current season only")
    parser.add_argument("--max-round", type=int, default=None, help="Max round for 2026 ingest")
    args = parser.parse_args()
    started = time.monotonic()

    if args.mock:
        logger.info("Generating mock data only")
        from backtest import generate_mock_data
        from assets import build_drivers_json

        build_drivers_json(use_openf1=True)
        generate_mock_data()
        _finish_outputs(mock=True)
        logger.info("Precompute pipeline complete in %.1fs", time.monotonic() - started)
        return 0

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
                logger.warning("Ingest returned no data and no cached parquet exists")
                from backtest import generate_mock_data

                generate_mock_data()
                _finish_outputs(mock=True)
                return 0
        except Exception as exc:
            logger.error("Ingest failed: %s", exc)
            if not _has_real_data():
                from backtest import generate_mock_data

                generate_mock_data()
                _finish_outputs(mock=True)
                return 0
            logger.info("Continuing with existing parquet data")
    else:
        from ingest import load_sessions

        logger.info("Skipped (--skip-ingest)")
        if load_sessions().empty:
            logger.warning("No parquet data, generating mock")
            from backtest import generate_mock_data

            generate_mock_data()
            _finish_outputs(mock=True)
            return 0

    step += 1
    _step(step, total_steps, "Build features")
    from features import build_features

    features = build_features()
    if features.empty:
        logger.warning("Feature build failed")
        if not _has_real_data():
            from backtest import generate_mock_data

            generate_mock_data()
            _finish_outputs(mock=True)
            return 0
        logger.error("Cannot proceed without features")
        return 1

    step += 1
    _step(step, total_steps, "Backtest + leaderboard + predictions")
    from backtest import run_backtest

    try:
        run_backtest(features)
    except Exception as exc:
        logger.error("Backtest failed: %s", exc)
        if not _has_real_data():
            from backtest import generate_mock_data

            generate_mock_data()
            _finish_outputs(mock=True)
            return 0
        return 1

    step += 1
    _step(step, total_steps, "Sync site/public/api (+ Mercedes 2026 What If)")
    _finish_outputs()

    elapsed = time.monotonic() - started
    logger.info("Precompute pipeline complete in %.1fs", elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
