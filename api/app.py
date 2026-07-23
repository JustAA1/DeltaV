"""DeltaV API — local serve for precomputed data and What If."""

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

from config import BACKTEST_SEASON, CURRENT_SEASON, LEADERBOARD_SEASONS, OUTPUTS_DIR, RACES_2026
from features import load_features
from model import load_model
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


@app.get("/api/drivers")
def get_drivers() -> dict:
    return _read_json("drivers.json")


@app.get("/api/predictions/{round}")
def get_predictions(round: int) -> dict:
    try:
        return _read_json(f"predictions_{round}.json")
    except HTTPException:
        raise HTTPException(status_code=404, detail=f"No predictions for round {round}")


@app.get("/api/backtest")
def get_backtest() -> dict:
    return _read_json("backtest.json")


@app.get("/api/leaderboard")
def get_leaderboard(season: int = BACKTEST_SEASON) -> dict:
    data = _read_json("leaderboard.json")
    seasons = data.get("seasons", {})
    key = str(season)
    if key not in seasons:
        raise HTTPException(status_code=404, detail=f"No leaderboard for season {season}")
    lb = seasons[key]
    from ingest import load_sessions
    from season_stats import build_season_stats

    lb = dict(lb)
    lb["stats"] = build_season_stats(load_sessions(), season, lb)
    return lb


@app.get("/api/podiumigami")
def get_podiumigami(season: int | None = None) -> dict:
    try:
        data = _read_json("podiums.json")
    except HTTPException:
        from ingest import load_sessions
        from podiumigami import write_podiumigami

        data = write_podiumigami(load_sessions())
    if season is None:
        return data
    if season not in LEADERBOARD_SEASONS:
        raise HTTPException(status_code=400, detail=f"Season {season} not supported")
    from podiumigami import slice_podiumigami

    try:
        return slice_podiumigami(data, season)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/races")
def get_races() -> dict:
    """List available prediction rounds."""
    rounds = []
    for f in Path(OUTPUTS_DIR).glob("predictions_*.json"):
        try:
            rnd = int(f.stem.split("_")[1])
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            rounds.append({"round": rnd, "event_name": data.get("event_name", ""), "season": data.get("season", CURRENT_SEASON)})
        except (ValueError, json.JSONDecodeError):
            continue
    rounds.sort(key=lambda x: x["round"])
    if not rounds:
        rounds = [{"round": k, "event_name": v, "season": CURRENT_SEASON} for k, v in RACES_2026.items()]
    return {"season": CURRENT_SEASON, "races": rounds}


class PredictRequest(BaseModel):
    round: int
    season: int = CURRENT_SEASON


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


@app.post("/api/predict")
def predict_live(req: PredictRequest) -> dict:
    """Run model inference for a race using latest features."""
    features = load_features()
    race_feat = features[(features["year"] == req.season) & (features["round"] == req.round)]
    if race_feat.empty:
        raise HTTPException(status_code=404, detail=f"No feature data for {req.season} R{req.round}")

    try:
        model = load_model()
        preds = model.predict_race(race_feat)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Model unavailable: {exc}") from exc

    pred_list = []
    for _, row in preds.iterrows():
        pred_list.append(
            {
                "driver_code": row["driver_key"],
                "driver_name": row["driver_name"],
                "team": row["team"],
                "predicted_position": int(row["predicted_position"]),
                "confidence": round(float(row["confidence"]), 4),
            }
        )

    event_name = race_feat["event_name"].iloc[0] if "event_name" in race_feat.columns else RACES_2026.get(req.round, "")
    return {
        "round": req.round,
        "season": req.season,
        "event_name": event_name,
        "predictions": pred_list,
        "live": True,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
