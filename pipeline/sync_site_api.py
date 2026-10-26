"""Copy pipeline outputs into site/public/api for static (Vercel) hosting."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from config import CURRENT_SEASON, OUTPUTS_DIR
from points_rules import get_points_system_changes

logger = logging.getLogger(__name__)

SITE_API_DIR = Path(__file__).resolve().parent.parent / "site" / "public" / "api"

COPY_NAMES = (
    "drivers.json",
    "leaderboard.json",
    "formula15.json",
    "reversed.json",
    "podiums.json",
    "points_system_changes.json",
)


def write_points_system_changes_json(dest_dir: Path | None = None) -> Path:
    out_dir = Path(OUTPUTS_DIR) if dest_dir is None else dest_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "points_system_changes.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(get_points_system_changes(), f, indent=2)
    return path


# Hosted remove-from-grid scenarios for the current season: (file, remove type, identifiers).
# Keep in sync with HOSTED_REMOVE_WHAT_IFS in site/src/lib/whatIfDefaults.ts.
HOSTED_REMOVE_WHAT_IFS: tuple[tuple[str, str, list[str]], ...] = (
    ("whatif_remove_2026_mercedes.json", "team", ["Mercedes"]),
    ("whatif_remove_2026_antonelli.json", "driver", ["ANT"]),
)


def write_hosted_what_if_defaults(dest_dir: Path | None = None) -> list[Path]:
    """Refresh the hosted remove-from-grid What If scenarios (current season).

    The 2021←2007 points-system payload is historical and not rewritten here.
    """
    out_dir = SITE_API_DIR if dest_dir is None else Path(dest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from whatif import compute_what_if

    written: list[Path] = []
    for filename, remove_type, identifiers in HOSTED_REMOVE_WHAT_IFS:
        try:
            payload = compute_what_if(
                season=CURRENT_SEASON,
                remove_type=remove_type,
                identifiers=identifiers,
            )
        except Exception as exc:
            logger.warning("Hosted What If refresh failed for %s: %s", filename, exc)
            continue
        path = out_dir / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Wrote hosted What If → %s", path)
        written.append(path)
    return written


def sync_replays() -> int:
    """Copy replay index + per-race JSON into site/public/api/replays/."""
    src = Path(OUTPUTS_DIR)
    SITE_API_DIR.mkdir(parents=True, exist_ok=True)
    replays_src = src / "replays"
    replays_dest = SITE_API_DIR / "replays"
    replays_dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    index_src = src / "replays_index.json"
    if index_src.exists():
        shutil.copy2(index_src, SITE_API_DIR / "replays_index.json")
        copied += 1

    if replays_src.is_dir():
        # Drop stale season_round files, then copy current set
        for stale in replays_dest.glob("*.json"):
            stale.unlink(missing_ok=True)
        for path in sorted(replays_src.glob("*.json")):
            shutil.copy2(path, replays_dest / path.name)
            copied += 1

    logger.info("Synced %d replay file(s) → %s", copied, SITE_API_DIR)
    return copied


def sync_site_api() -> None:
    """Publish JSON artifacts to site/public/api for Vercel."""
    src = Path(OUTPUTS_DIR)
    SITE_API_DIR.mkdir(parents=True, exist_ok=True)

    write_points_system_changes_json(src)

    # Drop leftover prediction / model artifacts if any remain
    for stale in SITE_API_DIR.glob("predictions_*.json"):
        stale.unlink(missing_ok=True)
    for orphan in ("backtest.json", "model.json", "races.json"):
        orphan_path = SITE_API_DIR / orphan
        if orphan_path.exists():
            orphan_path.unlink()

    copied = 0
    for name in COPY_NAMES:
        path = src / name
        if path.exists():
            shutil.copy2(path, SITE_API_DIR / name)
            copied += 1

    copied += len(write_hosted_what_if_defaults(SITE_API_DIR))

    copied += sync_replays()

    logger.info("Synced %d API files → %s", copied, SITE_API_DIR)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sync_site_api()
