"""Official formula1.com race-result URLs, keyed by season round."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

from config import CURRENT_SEASON, LEADERBOARD_SEASONS, OUTPUTS_DIR

logger = logging.getLogger(__name__)

UA = {"User-Agent": "DeltaV/1.0 (https://github.com; race-result links)"}
RESULTS_INDEX = "https://www.formula1.com/en/results/{year}/races"
RESULT_URL = "https://www.formula1.com/en/results/{year}/races/{race_id}/{slug}/race-result"
HREF_RE = re.compile(r"/en/results/(\d{4})/races/(\d+)/([a-z0-9\-]+)/race-result")

# F1.com slug → substrings that identify our FastF1/Jolpica event name.
SLUG_HINTS: dict[str, tuple[str, ...]] = {
    "70th-anniversary": ("70th anniversary", "70th"),
    "abu-dhabi": ("abu dhabi",),
    "argentina": ("argentine", "argentina"),
    "australia": ("australian", "australia"),
    "austria": ("austrian", "austria"),
    "azerbaijan": ("azerbaijan",),
    "bahrain": ("bahrain",),
    "barcelona-catalunya": ("barcelona",),
    "belgium": ("belgian", "belgium"),
    "brazil": ("brazilian", "brazil", "sao paulo", "são paulo"),
    "britain": ("british", "britain"),
    "caesar-s-palace": ("caesars palace", "caesar"),
    "canada": ("canadian", "canada"),
    "china": ("chinese", "china"),
    "eifel": ("eifel",),
    "emilia-romagna": ("emilia romagna", "imola"),
    "europe": ("european", "europe"),
    "france": ("french", "france"),
    "germany": ("german", "germany"),
    "great-britain": ("british", "great britain", "britain"),
    "hungary": ("hungarian", "hungary"),
    "india": ("indian", "india"),
    "italy": ("italian",),
    "japan": ("japanese", "japan"),
    "korea": ("korean", "korea"),
    "las-vegas": ("las vegas",),
    "luxembourg": ("luxembourg",),
    "malaysia": ("malaysian", "malaysia"),
    "mexico": ("mexico", "mexican"),
    "miami": ("miami",),
    "monaco": ("monaco",),
    "netherlands": ("dutch", "netherlands"),
    "pacific": ("pacific",),
    "portugal": ("portuguese", "portugal"),
    "qatar": ("qatar",),
    "russia": ("russian", "russia"),
    "sakhir": ("sakhir",),
    "san-marino": ("san marino",),
    "sao-paulo": ("sao paulo", "são paulo", "brazilian"),
    "saudi-arabia": ("saudi",),
    "singapore": ("singapore",),
    "south-africa": ("south african", "south africa"),
    "south-korea": ("korean", "korea"),
    "spain": ("spanish",),
    "styria": ("styrian", "styria"),
    "sweden": ("swedish", "sweden"),
    "switzerland": ("swiss", "switzerland"),
    "turkey": ("turkish", "turkey"),
    "tuscany": ("tuscan", "tuscany"),
    "united-states": ("united states",),
    "usa": ("united states", "usa"),
    "usa-east": ("united states",),
    "usa-west": ("united states west", "united states grand prix west", "us west"),
}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().replace("'", "").replace(".", "").split())


def _slug_matches(slug: str, event_name: str) -> bool:
    ev = _fold(event_name)
    if slug in {"united-states", "usa", "usa-east"} and "west" in ev:
        return False
    if slug in {"brazil", "sao-paulo"} and "anniversary" in ev:
        return False
    hints = SLUG_HINTS.get(slug)
    if hints:
        return any(h in ev for h in hints)
    token = slug.replace("-", " ")
    return token in ev or token.rstrip("n") in ev


def fetch_season_index(year: int) -> list[tuple[str, str]]:
    """Return unique (race_id, slug) pairs in page order."""
    url = RESULTS_INDEX.format(year=year)
    resp = requests.get(url, headers=UA, timeout=45)
    resp.raise_for_status()
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for match in HREF_RE.finditer(resp.text):
        href_year, race_id, slug = match.group(1), match.group(2), match.group(3)
        if int(href_year) != year:
            continue
        key = (race_id, slug)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def match_official_results(
    year: int,
    race_names: dict[str, str],
    rounds: list[int],
    index: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    unmatched = [(int(rnd), race_names.get(str(rnd), f"Round {rnd}")) for rnd in rounds]
    used: set[int] = set()
    results: list[dict[str, Any]] = []
    for race_id, slug in index:
        hit: tuple[int, str] | None = None
        for rnd, name in unmatched:
            if rnd in used:
                continue
            if _slug_matches(slug, name):
                hit = (rnd, name)
                break
        if hit is None:
            continue
        rnd, name = hit
        used.add(rnd)
        results.append(
            {
                "round": rnd,
                "name": name,
                "f1_id": int(race_id),
                "slug": slug,
                "url": RESULT_URL.format(year=year, race_id=race_id, slug=slug),
            }
        )
    results.sort(key=lambda r: int(r["round"]))
    return results


def attach_official_results(
    leaderboard: dict[str, Any],
    *,
    cache_path: Path | None = None,
    refresh_current: bool = True,
) -> dict[str, Any]:
    """Add ``official_results`` to each season using formula1.com race IDs."""
    cache_path = cache_path or Path(OUTPUTS_DIR) / "f1_results_index.json"
    cache: dict[str, list[list[str]]] = {}
    if cache_path.is_file():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            cache = {str(k): v for k, v in (raw.get("seasons") or raw).items()}
        except (OSError, json.JSONDecodeError, AttributeError):
            cache = {}

    seasons = leaderboard.get("seasons") or {}
    years = sorted(int(y) for y in seasons if str(y).isdigit() and int(y) in LEADERBOARD_SEASONS)
    for year in years:
        key = str(year)
        need_fetch = key not in cache or (refresh_current and year == CURRENT_SEASON)
        if need_fetch:
            try:
                pairs = fetch_season_index(year)
                cache[key] = [[rid, slug] for rid, slug in pairs]
                logger.info("F1.com results index %d: %d races", year, len(pairs))
                time.sleep(0.2)
            except Exception as exc:
                logger.warning("F1.com results index %d failed: %s", year, exc)
                pairs = [(a, b) for a, b in cache.get(key, [])]
        else:
            pairs = [(a, b) for a, b in cache.get(key, [])]
        lb = seasons[key]
        lb["official_results"] = match_official_results(
            year,
            lb.get("race_names") or {},
            list(lb.get("rounds") or []),
            pairs,
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"seasons": cache}, indent=2), encoding="utf-8")
    return leaderboard


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--leaderboard", type=str, default=None)
    args = parser.parse_args()
    path = Path(args.leaderboard or Path(OUTPUTS_DIR) / "leaderboard.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    attach_official_results(data, refresh_current=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Updated official_results in %s", path)
