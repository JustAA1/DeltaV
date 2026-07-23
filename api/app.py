"""DeltaV API — local What If compute (+ health). Static JSON is served by the site."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Resolve pipeline modules (ingest, whatif, outputs, …) for this deploy target.
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import BACKTEST_SEASON, CURRENT_SEASON, LEADERBOARD_SEASONS, OUTPUTS_DIR
from whatif import (
    compute_points_system_what_if,
    compute_what_if,
    get_constructor_champions,
    get_points_system_changes,
    get_what_if_options,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="DeltaV API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_json(filename: str) -> Any:
    path = os.path.join(OUTPUTS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "season": CURRENT_SEASON}


class WhatIfRemove(BaseModel):
    type: str  # "driver" | "team"
    name: str
    id: str | None = None


class WhatIfRequest(BaseModel):
    season: int
    removes: list[WhatIfRemove]
    championship: str = "drivers"


class PointsWhatIfRequest(BaseModel):
    season: int
    points_from: int
    championship: str = "drivers"


@app.get("/api/what-if/constructor-champions")
def what_if_constructor_champions() -> dict:
    try:
        return get_constructor_champions(_read_json("leaderboard.json"))
    except HTTPException:
        raise
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/what-if/points-system-changes")
def what_if_points_system_changes() -> dict:
    return get_points_system_changes()


@app.get("/api/what-if/options")
def what_if_options(season: int = BACKTEST_SEASON) -> dict:
    if season not in LEADERBOARD_SEASONS:
        raise HTTPException(status_code=400, detail=f"Season {season} not supported")
    try:
        return get_what_if_options(season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/what-if")
def what_if_leaderboard(req: WhatIfRequest) -> dict:
    if not req.removes:
        raise HTTPException(status_code=400, detail="At least one removal is required")
    remove_types = {r.type for r in req.removes}
    if len(remove_types) != 1:
        raise HTTPException(
            status_code=400,
            detail="All removals must be the same type (driver or team)",
        )
    remove_type = remove_types.pop()
    identifiers: list[str] = []
    for item in req.removes:
        identifier = item.id or item.name if item.type == "driver" else item.name
        if not identifier:
            raise HTTPException(status_code=400, detail="Each removal needs a name or id")
        identifiers.append(identifier)
    try:
        return compute_what_if(
            season=req.season,
            remove_type=remove_type,
            identifiers=identifiers,
            championship=req.championship,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/what-if/points-system")
def what_if_points_system(req: PointsWhatIfRequest) -> dict:
    try:
        return compute_points_system_what_if(
            season=req.season,
            points_from_year=req.points_from,
            championship=req.championship,
            precomputed=_read_json("leaderboard.json"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
