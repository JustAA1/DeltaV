"""Fetch driver headshots and team logos for the site."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from pathlib import Path

import requests

from config import (
    CURRENT_SEASON,
    LEADERBOARD_SEASONS,
    OUTPUTS_DIR,
    RACES_2026,
    SITE_PUBLIC_DIR,
    get_team_color,
    normalize_team,
)

logger = logging.getLogger(__name__)

OPENF1_BASE = "https://api.openf1.org/v1"
DRIVERS_JSON = os.path.join(OUTPUTS_DIR, "drivers.json")
HEADSHOTS_DIR = os.path.join(SITE_PUBLIC_DIR, "drivers")
TEAMS_DIR = os.path.join(SITE_PUBLIC_DIR, "teams")

UA = {"User-Agent": "Mozilla/5.0 (DeltaV/1.0)"}

# Fallback 2026 grid when OpenF1 unavailable
FALLBACK_DRIVERS_2026 = [
    {"code": "NOR", "name": "Lando Norris", "team": "McLaren", "number": 1},
    {"code": "PIA", "name": "Oscar Piastri", "team": "McLaren", "number": 81},
    {"code": "VER", "name": "Max Verstappen", "team": "Red Bull Racing", "number": 3},
    {"code": "TSU", "name": "Yuki Tsunoda", "team": "Red Bull Racing", "number": 22},
    {"code": "LEC", "name": "Charles Leclerc", "team": "Ferrari", "number": 16},
    {"code": "HAM", "name": "Lewis Hamilton", "team": "Ferrari", "number": 44},
    {"code": "RUS", "name": "George Russell", "team": "Mercedes", "number": 63},
    {"code": "ANT", "name": "Andrea Kimi Antonelli", "team": "Mercedes", "number": 12},
    {"code": "ALO", "name": "Fernando Alonso", "team": "Aston Martin", "number": 14},
    {"code": "STR", "name": "Lance Stroll", "team": "Aston Martin", "number": 18},
    {"code": "GAS", "name": "Pierre Gasly", "team": "Alpine", "number": 10},
    {"code": "COL", "name": "Franco Colapinto", "team": "Alpine", "number": 43},
    {"code": "ALB", "name": "Alexander Albon", "team": "Williams", "number": 23},
    {"code": "SAI", "name": "Carlos Sainz", "team": "Williams", "number": 55},
    {"code": "HAD", "name": "Isack Hadjar", "team": "Racing Bulls", "number": 6},
    {"code": "LAW", "name": "Liam Lawson", "team": "Racing Bulls", "number": 30},
    {"code": "OCO", "name": "Esteban Ocon", "team": "Haas F1 Team", "number": 31},
    {"code": "BEA", "name": "Oliver Bearman", "team": "Haas F1 Team", "number": 87},
    {"code": "BOR", "name": "Gabriel Bortoleto", "team": "Audi", "number": 5},
    {"code": "HUL", "name": "Nico Hülkenberg", "team": "Audi", "number": 27},
    {"code": "BOT", "name": "Valtteri Bottas", "team": "Cadillac", "number": 77},
    {"code": "PER", "name": "Sergio Pérez", "team": "Cadillac", "number": 11},
]

# Known F1 CDN slug overrides when the auto pattern fails (keyed by person id)
HEADSHOT_OVERRIDES: dict[str, str] = {
    "raikkonen-kimi": "https://media.formula1.com/content/dam/fom-website/drivers/K/KIMRAI01_Kimi_Raikkonen/kimrai01.png.transform/2col/image.png",
    "vettel-sebastian": "https://media.formula1.com/content/dam/fom-website/drivers/S/SEBVET01_Sebastian_Vettel/sebvet01.png.transform/2col/image.png",
    "zhou-guanyu": "https://media.formula1.com/content/dam/fom-website/drivers/G/GUAZHO01_Guanyu_Zhou/guazho01.png.transform/2col/image.png",
    "hulkenberg-nico": "https://media.formula1.com/content/dam/fom-website/drivers/N/NICHUL01_Nico_Hulkenberg/nichul01.png.transform/2col/image.png",
    "perez-sergio": "https://media.formula1.com/content/dam/fom-website/drivers/S/SERPER01_Sergio_Perez/serper01.png.transform/2col/image.png",
    "antonelli-kimi": "https://media.formula1.com/content/dam/fom-website/drivers/K/ANDANT01_Kimi_Antonelli/andant01.png.transform/2col/image.png",
}

# Legacy `{code}.png` files were downloaded for these people only.
# Never reuse a code file for a different driver who shared that tricode.
LEGACY_CODE_OWNERS: dict[str, str] = {
    **{d["code"].upper(): d["name"] for d in FALLBACK_DRIVERS_2026},
    "RAI": "Kimi Räikkönen",
    "VET": "Sebastian Vettel",
    "ZHO": "Guanyu Zhou",
    "RIC": "Daniel Ricciardo",
    "GRO": "Romain Grosjean",
    "MAG": "Kevin Magnussen",
    "KVY": "Daniil Kvyat",
    "GIO": "Antonio Giovinazzi",
    "KUB": "Robert Kubica",
    "MAZ": "Nikita Mazepin",
    "AIT": "Jack Aitken",
    "FIT": "Pietro Fittipaldi",
    "SAR": "Logan Sargeant",
    "MSC": "Mick Schumacher",  # on-disk msc.png is Mick, not Michael
    "DOO": "Jack Doohan",  # not Albers/Doornbos — doo.png is Doohan
}

TEAM_LOGO_SLUGS: dict[str, str] = {
    "Ferrari": "ferrari",
    "Mercedes": "mercedes",
    "McLaren": "mclaren",
    "Red Bull Racing": "red bull racing",
    "Williams": "williams",
    "Alpine": "alpine",
    "Aston Martin": "aston martin",
    "Haas F1 Team": "haas",
    "Racing Bulls": "rb",
    "Kick Sauber": "kick sauber",
    "Alfa Romeo": "alfa romeo",
    "AlphaTauri": "alphatauri",
    "Racing Point": "racing point",
    "Renault": "renault",
    "Audi": "audi",
    "Cadillac": "cadillac",
}


def _fetch_openf1_drivers(session_key: str | int = "latest") -> list[dict]:
    try:
        resp = requests.get(
            f"{OPENF1_BASE}/drivers",
            params={"session_key": session_key},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("OpenF1 drivers fetch failed: %s", exc)
        return []


def _clean_headshot_url(url: str) -> str:
    if not url:
        return ""
    url = url.replace("d_driver_fallback_image.png/", "")
    url = url.replace(".transform/1col/", ".transform/2col/")
    return url


def _download(url: str, dest: Path) -> bool:
    if not url:
        return dest.exists() and dest.stat().st_size > 0
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        resp = requests.get(url, timeout=12, headers=UA)
        resp.raise_for_status()
        if not resp.content or len(resp.content) < 400:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return True
    except Exception as exc:
        logger.debug("Download failed %s: %s", url, exc)
        return False


def _ascii_name(name: str) -> str:
    """Strip accents for F1 CDN path matching."""
    replacements = {
        "ä": "a", "ö": "o", "ü": "u", "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ñ": "n", "ç": "c", "Ä": "A", "Ö": "O", "Ü": "U", "É": "E", "ß": "ss",
        "ã": "a", "õ": "o", "ê": "e", "â": "a", "ô": "o", "è": "e", "ë": "e",
    }
    out = name
    for a, b in replacements.items():
        out = out.replace(a, b)
    return out


def _normalize_person_name(full: str) -> str:
    """Canonical person id string (accent-insensitive, collapsed variants)."""
    n = _ascii_name(full or "").lower().strip()
    n = re.sub(r"[^a-z0-9\s-]+", "", n)
    n = re.sub(r"\s+", " ", n)
    # Same driver, different official strings
    if "antonelli" in n:
        return "kimi antonelli"
    if n in {"sergio perez", "sergio pérez"}:
        return "sergio perez"
    return n


def _split_name(full: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"\s+", (full or "").strip()) if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], parts[0]
    given = parts[0]
    family = parts[-1]
    # "Andrea Kimi Antonelli" → Kimi Antonelli for CDN
    if len(parts) >= 3 and parts[0].lower() in {"andrea", "nyck", "pierre"}:
        given, family = parts[-2], parts[-1]
    # Jean-Éric Vergne style already split on spaces as Jean-Éric / Vergne
    return given, family


def person_image_stem(full_name: str) -> str:
    """Stable filesystem key from the person's name — never the radio tricode alone."""
    n = _normalize_person_name(full_name)
    parts = [p for p in n.split() if p]
    if not parts:
        return "unknown"
    if len(parts) == 1:
        return parts[0]
    family = parts[-1]
    given = "-".join(parts[:-1])
    return f"{family}-{given}"


def same_person(a: str, b: str) -> bool:
    return _normalize_person_name(a) == _normalize_person_name(b)


def _f1_cdn_headshot_urls(full_name: str) -> list[str]:
    given, family = _split_name(full_name)
    if not given or not family:
        return []
    g = _ascii_name(given)
    f = _ascii_name(family)
    # Drop hyphens inside tokens for CDN (Jean-Eric → Jean)
    g_cdn = g.replace("-", "")
    f_cdn = f.replace("-", "")
    slug = f"{g_cdn[:3].upper()}{f_cdn[:3].upper()}01_{g_cdn}_{f_cdn}"
    folder = g_cdn[0].upper()
    file = f"{g_cdn[:3].lower()}{f_cdn[:3].lower()}01.png"
    base = f"https://media.formula1.com/content/dam/fom-website/drivers/{folder}/{slug}/{file}"
    return [base + ".transform/2col/image.png", base]


def _legacy_code_path(code: str) -> Path:
    return Path(HEADSHOTS_DIR) / f"{(code or '').lower()}.png"


def _person_path(full_name: str) -> Path:
    return Path(HEADSHOTS_DIR) / f"{person_image_stem(full_name)}.png"


def _adopt_legacy_code_file(code: str, full_name: str) -> Path | None:
    """If `{code}.png` belongs to this person, copy it onto the name-based path."""
    legacy = _legacy_code_path(code)
    if not legacy.exists() or legacy.stat().st_size <= 0:
        return None
    owner = LEGACY_CODE_OWNERS.get((code or "").upper())
    if not owner or not same_person(owner, full_name):
        return None
    dest = _person_path(full_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(legacy, dest)
    return dest


def _ensure_headshot(code: str, full_name: str, openf1_url: str = "") -> str | None:
    """Download/resolve a headshot keyed by person name (not tricode alone)."""
    if not full_name and not code:
        return None
    name = full_name or code
    dest = _person_path(name)
    if dest.exists() and dest.stat().st_size > 0:
        return f"/drivers/{dest.stem}.png"

    adopted = _adopt_legacy_code_file(code, name)
    if adopted is not None and adopted.exists():
        return f"/drivers/{adopted.stem}.png"

    candidates: list[str] = []
    stem = person_image_stem(name)
    if stem in HEADSHOT_OVERRIDES:
        candidates.append(HEADSHOT_OVERRIDES[stem])
    cleaned = _clean_headshot_url(openf1_url)
    if cleaned:
        candidates.append(cleaned)
    candidates.extend(_f1_cdn_headshot_urls(name))

    for url in candidates:
        if _download(url, dest):
            return f"/drivers/{dest.stem}.png"
    return None


def _team_slug(team: str) -> str:
    return TEAM_LOGO_SLUGS.get(normalize_team(team), team.lower())


def ensure_team_logo(team: str) -> str | None:
    """Download a team logo into /teams/<slug>.png (or .jpg saved as png name)."""
    canon = normalize_team(team)
    if not canon or canon == "Unknown":
        return None
    slug_file = re.sub(r"[^a-z0-9]+", "-", canon.lower()).strip("-")
    dest = Path(TEAMS_DIR) / f"{slug_file}.png"
    if dest.exists() and dest.stat().st_size > 0:
        return f"/teams/{slug_file}.png"

    logo_slug = _team_slug(canon)
    encoded = logo_slug.replace(" ", "%20")
    base = "https://media.formula1.com/image/upload/f_auto,c_limit,q_auto,w_200/content/dam/fom-website/2018-redesign-assets/team%20logos/"
    for ext in (".jpg", ".png"):
        if _download(base + encoded + ext, dest):
            return f"/teams/{slug_file}.png"
    return None


def _drivers_from_sessions() -> list[dict]:
    """Unique people across all leaderboard seasons (keyed by name, not tricode)."""
    try:
        from ingest import load_sessions

        sessions = load_sessions()
    except Exception:
        return []
    if sessions.empty:
        return []

    scoring = sessions[
        sessions["year"].isin(LEADERBOARD_SEASONS) & sessions["session"].isin(["R", "S"])
    ].copy()
    if scoring.empty:
        return []

    scoring["driver_key"] = scoring["driver_code"].fillna("").astype(str).str.upper()
    scoring["person"] = scoring["driver_name"].fillna("").astype(str).map(_normalize_person_name)
    out: list[dict] = []
    for person, grp in scoring.sort_values(["year", "round"]).groupby("person"):
        if not person:
            continue
        last = grp.iloc[-1]
        out.append(
            {
                "code": str(last.get("driver_key") or "").upper(),
                "name": str(last.get("driver_name") or person).strip(),
                "team": normalize_team(str(last.get("team") or "")),
                "number": int(last.get("driver_number") or 0) or None,
            }
        )
    return out


def fetch_all_headshots_and_logos() -> dict[str, str | None]:
    """Ensure headshots for every known person + logos for every known team."""
    Path(HEADSHOTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(TEAMS_DIR).mkdir(parents=True, exist_ok=True)

    logger.info("Fetching OpenF1 driver metadata…")
    openf1_by_code: dict[str, dict] = {}
    for d in _fetch_openf1_drivers():
        code = (d.get("name_acronym") or "").upper()
        if code:
            openf1_by_code[code] = d

    # Key roster by person name so tricode collisions stay distinct.
    roster: dict[str, dict] = {}
    for d in _drivers_from_sessions():
        roster[_normalize_person_name(d["name"])] = d
    for d in FALLBACK_DRIVERS_2026:
        roster.setdefault(_normalize_person_name(d["name"]), dict(d))

    for code, d in openf1_by_code.items():
        name = (d.get("full_name") or code).title()
        person = _normalize_person_name(name)
        team = normalize_team(d.get("team_name", "") or "")
        roster[person] = {
            "code": code,
            "name": name,
            "team": team or roster.get(person, {}).get("team", ""),
            "number": d.get("driver_number"),
            "headshot_url": d.get("headshot_url", ""),
        }

    total = len(roster)
    logger.info("Resolving headshots for %d drivers…", total)
    images: dict[str, str | None] = {}
    downloaded = 0
    cached = 0
    missing = 0
    for i, (person, meta) in enumerate(sorted(roster.items()), start=1):
        name = meta.get("name", person)
        dest = _person_path(name)
        already = dest.exists() and dest.stat().st_size > 0
        if already:
            if i == 1 or i % 50 == 0 or i == total:
                logger.info("  Headshots [%d/%d] cached… (%s)", i, total, name)
        else:
            logger.info("  Headshots [%d/%d] fetching %s…", i, total, name)
        img = _ensure_headshot(
            meta.get("code", ""),
            name,
            meta.get("headshot_url", ""),
        )
        images[person] = img
        if img and already:
            cached += 1
        elif img:
            downloaded += 1
        else:
            missing += 1
        time.sleep(0.05)

    teams = sorted({meta.get("team", "") for meta in roster.values() if meta.get("team")})
    logger.info("Resolving logos for %d teams…", len(teams))
    for i, team in enumerate(teams, start=1):
        logger.info("  Logos [%d/%d] %s", i, len(teams), team)
        ensure_team_logo(team)
        time.sleep(0.05)

    have = sum(1 for v in images.values() if v)
    logger.info(
        "Assets done: %d/%d headshots (%d cached, %d downloaded, %d missing)",
        have,
        len(images),
        cached,
        downloaded,
        missing,
    )
    return images


def build_drivers_json(use_openf1: bool = True) -> dict:
    """Build drivers metadata JSON for the site (current grid + image paths)."""
    Path(OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(HEADSHOTS_DIR).mkdir(parents=True, exist_ok=True)

    logger.info("Building drivers.json…")
    if use_openf1:
        fetch_all_headshots_and_logos()

    drivers_out: list[dict] = []
    openf1_data = _fetch_openf1_drivers() if use_openf1 else []

    if openf1_data:
        seen: set[str] = set()
        for d in openf1_data:
            code = (d.get("name_acronym") or "").upper()
            if not code or code in seen:
                continue
            seen.add(code)
            name = (d.get("full_name") or code).title()
            team = normalize_team(d.get("team_name", "") or "")
            color = get_team_color(team)
            image = _ensure_headshot(code, name, d.get("headshot_url", ""))
            drivers_out.append(
                {
                    "code": code,
                    "name": name,
                    "team": team,
                    "number": d.get("driver_number"),
                    "color": color,
                    "image": image,
                }
            )
    else:
        if os.path.exists(DRIVERS_JSON):
            try:
                with open(DRIVERS_JSON, encoding="utf-8") as f:
                    existing = json.load(f)
                if any(d.get("image") for d in existing.get("drivers", [])):
                    logger.info("Keeping existing drivers.json with cached headshots")
                    return existing
            except Exception:
                pass
        logger.info("Using fallback driver list")
        for d in FALLBACK_DRIVERS_2026:
            team = normalize_team(d["team"])
            code = d["code"]
            drivers_out.append(
                {
                    "code": code,
                    "name": d["name"],
                    "team": team,
                    "number": d["number"],
                    "color": get_team_color(team),
                    "image": _ensure_headshot(code, d["name"]),
                }
            )

    payload = {
        "season": CURRENT_SEASON,
        "drivers": drivers_out,
        "races": {str(k): v for k, v in RACES_2026.items()},
    }
    with open(DRIVERS_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Wrote %d drivers to %s", len(drivers_out), DRIVERS_JSON)
    return payload


def image_for_driver(code: str, name: str | None = None) -> str | None:
    """Resolve a headshot path for a specific person.

    Requires ``name`` whenever tricodes can collide (ALB, DOO, MSC, VER, …).
    Code-only lookup is only allowed when the legacy `{code}.png` is known to
    belong to a single canonical owner and no name was provided.
    """
    if name:
        dest = _person_path(name)
        if dest.exists() and dest.stat().st_size > 0:
            return f"/drivers/{dest.stem}.png"
        adopted = _adopt_legacy_code_file(code, name)
        if adopted is not None and adopted.exists():
            return f"/drivers/{adopted.stem}.png"
        return None

    # Name missing: only return a legacy code file if that code is unambiguous
    # in LEGACY_CODE_OWNERS (still may be wrong historically — prefer passing name).
    owner = LEGACY_CODE_OWNERS.get((code or "").upper())
    if not owner:
        return None
    return image_for_driver(code, owner)


def logo_for_team(team: str) -> str | None:
    return ensure_team_logo(team)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_drivers_json()
