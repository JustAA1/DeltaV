"""Central configuration for the DeltaV data pipeline."""

from __future__ import annotations

from pathlib import Path

SEASONS: list[int] = list(range(2018, 2027))  # 2018–2026
INGEST_SEASONS: list[int] = list(range(2020, 2027))  # race data for leaderboards / replays / what-if
LEADERBOARD_SEASONS: list[int] = list(range(1980, 2027))
CURRENT_SEASON: int = 2026
BACKTEST_SEASON: int = 2026  # default season for local What If API
DEFAULT_TEAM_COLOR: str = "#888888"

# Midfield-only championship (big 4 removed + races rescored).
FORMULA15_START: int = 2021
FORMULA15_TEAMS: list[str] = [
    "Mercedes",
    "Red Bull Racing",
    "Ferrari",
    "McLaren",
]
# Extra Formula 1.5-only notes (not shown on the main championship chart).
# Midfield drivers' guest drives for a big-4 team are noted automatically.
FORMULA15_NOTES: dict[int, list[str]] = {}

# Drivers' championship dropped-scores (constructors counted all from 1979+).
# 1981–1990: best 11 overall. 1980: best 5 from each half of a 14-race season.
DRIVERS_BEST_N_RESULTS: dict[int, int] = {year: 11 for year in range(1981, 1991)}
# year -> (first_half_race_count, best_from_first, best_from_second)
DRIVERS_SPLIT_BEST_N: dict[int, tuple[int, int, int]] = {
    1980: (7, 5, 5),  # best 5 of first 7 + best 5 of last 7
}

# Season notes shown under the championship chart (half points, DSQs, etc.).
CHAMPIONSHIP_NOTES: dict[int, list[str]] = {
    1984: [
        "Monaco: half points awarded after the race was stopped early due to rain.",
    ],
    1991: [
        "Australia: half points awarded after the race was stopped early due to rain.",
    ],
    1997: [
        "Michael Schumacher was disqualified from the Drivers' Championship after the Jerez collision with Jacques Villeneuve.",
    ],
    2007: [
        "McLaren was disqualified from the Constructors' Championship (Spygate).",
    ],
    2009: [
        "Malaysia: half points awarded after the race was stopped early due to rain.",
    ],
    2014: [
        "Abu Dhabi: double points awarded for the season finale.",
    ],
    2021: [
        "Belgium (Spa): half points awarded after the race was stopped early due to rain.",
    ],
}

# Championship exclusions (still plotted; marked DQ in the standings).
# Drivers matched on normalized full name; constructors on normalized team name.
DRIVER_CHAMPIONSHIP_DSQ: dict[int, tuple[str, ...]] = {
    1997: ("michael schumacher",),
}
CONSTRUCTOR_CHAMPIONSHIP_DSQ: dict[int, tuple[str, ...]] = {
    2007: ("mclaren",),
}

# Recency weighting for training samples. 2026 is a new regulation cycle, so
# older seasons are less representative of current car performance.
RECENCY_DECAY: float = 0.6          # per-season multiplicative decay
REG_CYCLE_START: int = 2026         # first season of the current regulation set
PRE_REG_CYCLE_WEIGHT: float = 0.4   # extra multiplier for pre-reg-cycle seasons

# Canonical F1 team colors (current + era-correct historical liveries)
TEAM_COLORS: dict[str, str] = {
    # Current / recent grid
    "McLaren": "#FF8000",
    "Mercedes": "#27F4D2",
    "Red Bull Racing": "#3671C6",
    "Ferrari": "#E8002D",
    "Williams": "#64C4FF",
    "Racing Bulls": "#6692FF",
    "Audi": "#F50537",
    "Alpine": "#FF87BC",
    "Haas F1 Team": "#B6BABD",
    "Cadillac": "#A7ADB2",
    "Kick Sauber": "#52E252",
    "Aston Martin": "#229971",
    # Historical / alternate names (keep era identity for leaderboard colors)
    "Red Bull": "#3671C6",
    "Oracle Red Bull Racing": "#3671C6",
    "AlphaTauri": "#2B4562",
    "RB": "#6692FF",
    "Visa Cash App RB": "#6692FF",
    "Sauber": "#9B0000",
    "Stake F1 Team Kick Sauber": "#52E252",
    "Alfa Romeo": "#900000",
    "Alfa Romeo Racing": "#900000",
    "Alpha Romeo": "#900000",
    "Haas": "#B6BABD",
    "Haas F1": "#B6BABD",
    "Toro Rosso": "#469BFF",
    "Renault": "#FFF500",
    "Racing Point": "#F596C8",
    "Force India": "#F596C8",
    "Williams Racing": "#64C4FF",
    "McLaren Formula 1 Team": "#FF8000",
    "Mercedes-AMG PETRONAS F1 Team": "#27F4D2",
    "Scuderia Ferrari": "#E8002D",
    "Alpine F1 Team": "#FF87BC",
    "Aston Martin Aramco": "#229971",
    "Aston Martin Cognizant": "#006F62",
    # Pre-2020 grid
    "Lotus F1": "#FFB800",
    "Lotus": "#FFB800",
    "Manor Marussia F1 Team": "#B1001F",
    "Manor Marussia": "#B1001F",
    "Manor": "#B1001F",
    "Marussia": "#6E0000",
    "Caterham": "#005A2F",
    "Sauber F1 Team": "#9B0000",
    # 2005–2013 era
    "BMW Sauber": "#FFFFFF",
    "Toyota": "#EB0A1E",
    "Honda": "#FFFFFF",
    "Brawn": "#C8FF00",
    "Brawn GP": "#C8FF00",
    "Super Aguri": "#FFFFFF",
    "Midland": "#E10600",
    "MF1 Racing": "#E10600",
    "Spyker": "#F36C21",
    "Spyker MF1": "#F36C21",
    "Jordan": "#FFD700",
    "Jordan Grand Prix": "#FFD700",
    "Minardi": "#000000",
    "BAR": "#FFFFFF",
    "BAR Honda": "#FFFFFF",
    "British American Racing": "#FFFFFF",
    "HRT": "#A29167",
    "HRT F1 Team": "#A29167",
    "Hispania Racing": "#A29167",
    "Virgin": "#F40000",
    "Virgin Racing": "#F40000",
    "Marussia Virgin Racing": "#F40000",
    "Lotus Racing": "#FFB800",
    "Team Lotus": "#FFB800",
    # 1990–2004 era
    "Benetton": "#00B140",
    "Benetton Formula": "#00B140",
    "Tyrrell": "#0033A0",
    "Ligier": "#0072BB",
    "Prost": "#0072BB",
    "Prost Grand Prix": "#0072BB",
    "Footwork": "#FFFFFF",
    "Arrows": "#FF6600",
    "Stewart": "#FFFFFF",
    "Stewart Grand Prix": "#FFFFFF",
    "Jaguar": "#006F62",
    "Jaguar Racing": "#006F62",
    "Pacific": "#FF6600",
    "Pacific Racing": "#FF6600",
    "Forti": "#FFD700",
    "Simtek": "#6E0000",
    "Larrousse": "#FFD700",
    "Dallara": "#FF0000",
    "Lola": "#E10600",
    "MasterCard Lola": "#E10600",
    "March": "#009639",
    "Leyton House": "#00A3E0",
    "Brabham": "#0055A5",
    "Fondmetal": "#FFD700",
    "Andrea Moda": "#000000",
    "Coloni": "#FFD700",
    "AGS": "#FFFFFF",
    "Onyx": "#FFFFFF",
    "Euro Brun": "#FF6600",
    "Osella": "#FFFFFF",
    "Life": "#FFD700",
    "Zakspeed": "#E10600",
    "Rial": "#FFD700",
    # 1980s extras
    "Toleman": "#FFD700",
    "Spirit": "#FFFFFF",
    "RAM": "#FF6600",
    "Theodore": "#FFFFFF",
    "Ensign": "#FF6600",
    "Fittipaldi": "#FFD700",
    "Shadow": "#000000",
    "ATS": "#FFD700",
}

# Branding / spelling variants only — do NOT collapse distinct historical teams
# (e.g. Alfa Romeo ≠ Kick Sauber) so leaderboard colors stay era-correct.
TEAM_ALIASES: dict[str, str] = {
    "Red Bull": "Red Bull Racing",
    "Oracle Red Bull Racing": "Red Bull Racing",
    "RB": "Racing Bulls",
    "Visa Cash App RB": "Racing Bulls",
    "Stake F1 Team Kick Sauber": "Kick Sauber",
    "Haas": "Haas F1 Team",
    "Haas F1": "Haas F1 Team",
    "Williams Racing": "Williams",
    "McLaren Formula 1 Team": "McLaren",
    "Mercedes-AMG PETRONAS F1 Team": "Mercedes",
    "Scuderia Ferrari": "Ferrari",
    "Alpine F1 Team": "Alpine",
    "Aston Martin Aramco": "Aston Martin",
    "Aston Martin Cognizant": "Aston Martin",
    "Alfa Romeo Racing": "Alfa Romeo",
    "Alpha Romeo": "Alfa Romeo",
    "Lotus": "Team Lotus",
    "Manor Marussia F1 Team": "Manor",
    "Manor Marussia": "Manor",
    "Sauber F1 Team": "Sauber",
    "Brawn GP": "Brawn",
    "BAR Honda": "BAR",
    "British American Racing": "BAR",
    "Jordan Grand Prix": "Jordan",
    "MF1 Racing": "Midland",
    "Spyker MF1": "Spyker",
    "HRT F1 Team": "HRT",
    "Hispania Racing": "HRT",
    "Virgin Racing": "Virgin",
    "Marussia Virgin Racing": "Virgin",
    "Benetton Formula": "Benetton",
    "Prost Grand Prix": "Prost",
    "Stewart Grand Prix": "Stewart",
    "Jaguar Racing": "Jaguar",
    "Pacific Racing": "Pacific",
    "MasterCard Lola": "Lola",
    "Leyton House": "March",
}

# 2026 calendar (round -> event name). Saudi was cancelled; Bahrain was moved to
# Kuala Lumpur as round 16 (23 races).
RACES_2026: dict[int, str] = {
    1: "Australian Grand Prix",
    2: "Chinese Grand Prix",
    3: "Japanese Grand Prix",
    4: "Miami Grand Prix",
    5: "Canadian Grand Prix",
    6: "Monaco Grand Prix",
    7: "Barcelona Grand Prix",
    8: "Austrian Grand Prix",
    9: "British Grand Prix",
    10: "Belgian Grand Prix",
    11: "Hungarian Grand Prix",
    12: "Dutch Grand Prix",
    13: "Italian Grand Prix",
    14: "Madrid Grand Prix",
    15: "Azerbaijan Grand Prix",
    16: "Bahrain Grand Prix",
    17: "Singapore Grand Prix",
    18: "United States Grand Prix",
    19: "Mexico City Grand Prix",
    20: "São Paulo Grand Prix",
    21: "Las Vegas Grand Prix",
    22: "Qatar Grand Prix",
    23: "Abu Dhabi Grand Prix",
}

# Sprint weekends in 2026 (round numbers with a sprint race)
SPRINT_ROUNDS_2026: list[int] = [2, 4, 5, 9, 12, 17]

POINTS_SYSTEM = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
SPRINT_POINTS_SYSTEM = [8, 7, 6, 5, 4, 3, 2, 1]

_PIPELINE_ROOT = Path(__file__).resolve().parent
DATA_DIR = str(_PIPELINE_ROOT / "data")
CACHE_DIR = str(_PIPELINE_ROOT / "data" / "cache")
OUTPUTS_DIR = str(_PIPELINE_ROOT / "outputs")
PARQUET_PATH = str(_PIPELINE_ROOT / "data" / "sessions.parquet")
SITE_PUBLIC_DIR = str(_PIPELINE_ROOT.parent / "site" / "public")


def display_event_name(year: int, rnd: int, fallback: str = "") -> str:
    """Prefer the canonical 2026 calendar name when FastF1 still uses an old title."""
    if year == CURRENT_SEASON and rnd in RACES_2026:
        return RACES_2026[rnd]
    return fallback or f"Round {rnd}"


def normalize_team(team: str) -> str:
    """Return canonical team name."""
    if not team:
        return "Unknown"
    return TEAM_ALIASES.get(team, team)


def get_team_color(name: str | None) -> str:
    """Look up team color with alias normalization and fallback."""
    if not name:
        return DEFAULT_TEAM_COLOR
    # Prefer the exact historical name (e.g. Cognizant green) before aliasing.
    if name in TEAM_COLORS:
        return TEAM_COLORS[name]
    canonical = normalize_team(name)
    if canonical in TEAM_COLORS:
        return TEAM_COLORS[canonical]
    team_lower = canonical.lower()
    for team, color in TEAM_COLORS.items():
        if team.lower() in team_lower or team_lower in team.lower():
            return color
    return DEFAULT_TEAM_COLOR
