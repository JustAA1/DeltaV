"""Copy pipeline outputs into site/public/api for static (Vercel) hosting."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from config import CURRENT_SEASON, OUTPUTS_DIR, RACES_2026
from points_rules import get_points_system_changes

logger = logging.getLogger(__name__)

SITE_API_DIR = Path(__file__).resolve().parent.parent / "site" / "public" / "api"

COPY_NAMES = (
    "drivers.json",
    "leaderboard.json",
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


def write_races_json(dest_dir: Path | None = None) -> Path:
    """Build races.json from prediction files (static site race selector)."""
    out_dir = Path(OUTPUTS_DIR) if dest_dir is None else dest_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rounds: list[dict] = []
    for f in sorted(Path(OUTPUTS_DIR).glob("predictions_*.json")):
        try:
            rnd = int(f.stem.split("_")[1])
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            rounds.append(
                {
                    "round": rnd,
                    "event_name": data.get("event_name", ""),
                    "season": data.get("season", CURRENT_SEASON),
                }
            )
        except (ValueError, json.JSONDecodeError, OSError):
            continue
    rounds.sort(key=lambda x: x["round"])
    if not rounds:
        rounds = [
            {"round": k, "event_name": v, "season": CURRENT_SEASON} for k, v in RACES_2026.items()
        ]
    path = out_dir / "races.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"season": CURRENT_SEASON, "races": rounds}, f, indent=2)
    return path


def write_hosted_what_if_defaults(dest_dir: Path | None = None) -> Path | None:
    """Refresh the hosted remove-from-grid What If default (Mercedes, current season).

    The 2021←2007 points-system payload is historical and not rewritten here.
    """
    out_dir = SITE_API_DIR if dest_dir is None else Path(dest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from whatif import compute_what_if

        payload = compute_what_if(
            season=CURRENT_SEASON,
            remove_type="team",
            identifiers=["Mercedes"],
        )
    except Exception as exc:
        logger.warning("Hosted What If refresh failed: %s", exc)
        return None

    path = out_dir / "whatif_remove_2026_mercedes.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote hosted What If → %s", path)
    return path


def sync_site_api() -> None:
    """Publish JSON artifacts to site/public/api for Vercel."""
    src = Path(OUTPUTS_DIR)
    SITE_API_DIR.mkdir(parents=True, exist_ok=True)

    write_races_json(src)
    write_points_system_changes_json(src)

    # Drop stale prediction rounds (and unused artifacts) before copying the current set
    for stale in SITE_API_DIR.glob("predictions_*.json"):
        stale.unlink(missing_ok=True)
    for orphan in ("backtest.json", "model.json"):
        orphan_path = SITE_API_DIR / orphan
        if orphan_path.exists():
            orphan_path.unlink()

    copied = 0
    for name in COPY_NAMES:
        path = src / name
        if path.exists():
            shutil.copy2(path, SITE_API_DIR / name)
            copied += 1

    races_src = src / "races.json"
    if races_src.exists():
        shutil.copy2(races_src, SITE_API_DIR / "races.json")
        copied += 1

    for path in src.glob("predictions_*.json"):
        shutil.copy2(path, SITE_API_DIR / path.name)
        copied += 1

    if write_hosted_what_if_defaults(SITE_API_DIR) is not None:
        copied += 1

    logger.info("Synced %d API files → %s", copied, SITE_API_DIR)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sync_site_api()
