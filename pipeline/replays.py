"""Build compact race-replay JSON from FastF1 position telemetry.

Each race becomes site/public/api/replays/{season}_{round}.json with:
  - smoothed track outline + corner markers, quantized with a uniform scale so
    the circuit keeps its true aspect ratio (see Projection / track.q_w, q_h)
  - per-driver X/Y at 1 Hz (-1 = not on track / retired)
  - per-driver race progress in hundredths of a lap for live running order
  - tyre stints, pit stops, SC/VSC/red-flag windows, lap markers, race control feed

Usage:
  python replays.py                     # 2026 completed races + sprints (auto)
  python replays.py --season 2026 --rounds 1,2,3
  python replays.py --season 2026 --max-round 11
  python replays.py --season 2026 --rounds 2,4,5,9 --session S
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import (
    CACHE_DIR,
    CURRENT_SEASON,
    OUTPUTS_DIR,
    RACES_2026,
    SPRINT_ROUNDS_2026,
    display_event_name,
    get_team_color,
)

logger = logging.getLogger(__name__)

Q_MAX = 1000
HZ = 1
CENTERLINE_POINTS = 700
# How quickly geometry takes over from lap timing after a crossing. 0.4 hands
# geometry full weight beyond ~13% of a lap either side of the start/finish line.
GEOM_WEIGHT_RAMP = 0.4
# Feed gap above which an interpolated GPS sample is too coarse to rank cars by.
MAX_GEOM_FEED_GAP_S = 1.5
# Allowed scatter (fraction of a lap) of lap crossings projected onto the
# centerline. Above this, lap timing and the position feed are not describing the
# same thing and geometry is abandoned for that race.
GEOM_ALIGN_TOL = 0.04
# Progress is stored as an integer scaled by this. Hundredths of a lap is ~59 m
# at Silverstone, too coarse to tell two cars apart, which made intervals in the
# positions panel land on 0.5 s steps; thousandths gives ~6 m.
PROG_SCALE = 1000
OUTLINE_POINTS = 220
# Status codes from FastF1 track_status
STATUS_SC = {"4"}
STATUS_VSC = {"6", "7"}
STATUS_RED = {"5"}
# Blue flags dominate race control and say nothing about the race picture
FEED_SKIP_FLAGS = {"BLUE"}


def _enable_cache() -> None:
    try:
        import fastf1

        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(CACHE_DIR)
    except Exception as exc:
        logger.warning("Could not enable FastF1 cache: %s", exc)


def _td_seconds(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timedelta):
        return float(value.total_seconds())
    try:
        return float(pd.Timedelta(value).total_seconds())
    except (TypeError, ValueError):
        return None


def _rotate_xy(x: np.ndarray, y: np.ndarray, degrees: float) -> tuple[np.ndarray, np.ndarray]:
    """Match FastF1's official track-plot rotation (clockwise degrees)."""
    angle = math.radians(degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    # [[cos, sin], [-sin, cos]] applied to row vectors
    xr = x * cos_a + y * sin_a
    yr = -x * sin_a + y * cos_a
    return xr, yr


class Projection:
    """Uniform world→quantized mapping that preserves the circuit's real shape.

    Scaling X and Y by their own spans (the previous behaviour) stretches every
    track to a square. One shared scale keeps the true aspect ratio; q_w / q_h
    tell the client how large the quantized box actually is.
    """

    def __init__(self, bounds: tuple[float, float, float, float]) -> None:
        min_x, max_x, min_y, max_y = bounds
        self.min_x = min_x
        self.min_y = min_y
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        self.scale = Q_MAX / max(span_x, span_y)
        self.q_w = int(round(span_x * self.scale))
        self.q_h = int(round(span_y * self.scale))

    def apply(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        qx = np.clip(np.round((x - self.min_x) * self.scale), 0, self.q_w).astype(int)
        qy = np.clip(np.round((y - self.min_y) * self.scale), 0, self.q_h).astype(int)
        return qx, qy


def _resample_closed_curve(x: np.ndarray, y: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Smooth a noisy GPS loop and resample it evenly by arc length.

    The raw reference lap is only ~350 samples, so drawing it directly looks
    jagged. A periodic moving average removes GPS jitter, then Catmull-Rom
    interpolation between arc-length-spaced knots gives a clean outline.
    """
    if len(x) < 8:
        return x, y

    # Periodic moving average (window scales with input density)
    win = max(3, min(11, (len(x) // 40) * 2 + 1))
    kernel = np.ones(win) / win
    xs = np.convolve(np.concatenate([x[-win:], x, x[:win]]), kernel, mode="same")[win:-win]
    ys = np.convolve(np.concatenate([y[-win:], y, y[:win]]), kernel, mode="same")[win:-win]

    # Close the loop, then walk it at uniform arc length
    xs = np.append(xs, xs[0])
    ys = np.append(ys, ys[0])
    seg = np.hypot(np.diff(xs), np.diff(ys))
    dist = np.concatenate([[0.0], np.cumsum(seg)])
    total = dist[-1]
    if total <= 0:
        return x, y
    targets = np.linspace(0.0, total, n, endpoint=False)

    # Catmull-Rom through the arc-length knots keeps curvature smooth
    px = np.interp(targets, dist, xs)
    py = np.interp(targets, dist, ys)
    step = total / n
    prev_x = np.interp((targets - step) % total, dist, xs)
    prev_y = np.interp((targets - step) % total, dist, ys)
    next_x = np.interp((targets + step) % total, dist, xs)
    next_y = np.interp((targets + step) % total, dist, ys)
    sx = 0.25 * prev_x + 0.5 * px + 0.25 * next_x
    sy = 0.25 * prev_y + 0.5 * py + 0.25 * next_y
    return sx, sy


def _polyline(x: np.ndarray, y: np.ndarray, n: int) -> list[list[int]]:
    if len(x) == 0:
        return []
    if len(x) <= n:
        pts = [[int(a), int(b)] for a, b in zip(x, y)]
    else:
        idx = np.linspace(0, len(x) - 1, n).astype(int)
        pts = [[int(x[i]), int(y[i])] for i in idx]
    # Explicitly close the loop for the renderer
    if len(pts) >= 2 and pts[0] != pts[-1]:
        pts.append([pts[0][0], pts[0][1]])
    return pts


def _race_t0_seconds(laps: pd.DataFrame) -> float:
    """Lights-out ≈ earliest Lap 1 LapStartTime across the grid."""
    if laps is None or laps.empty or "LapNumber" not in laps.columns:
        return 0.0
    first = laps[laps["LapNumber"] == 1]
    if first.empty:
        first = laps
    times = [_td_seconds(v) for v in first.get("LapStartTime", [])]
    times = [t for t in times if t is not None]
    return float(min(times)) if times else 0.0


MAX_CENTERLINE_LAPS = 140
SINGLE_LAP_MIN_POINTS = 220


def _dedupe_consecutive(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Drop repeated coordinates — the GPS feed holds stale values."""
    if len(x) < 2:
        return x, y
    keep = np.concatenate([[True], (np.diff(x) != 0) | (np.diff(y) != 0)])
    return x[keep], y[keep]


def _clean_lap_candidates(laps: pd.DataFrame) -> pd.DataFrame:
    candidates = laps.copy()
    if "IsAccurate" in candidates.columns:
        accurate = candidates[candidates["IsAccurate"] == True]  # noqa: E712
        if not accurate.empty:
            candidates = accurate
    if "PitInTime" in candidates.columns:
        candidates = candidates[candidates["PitInTime"].isna()]
    if "PitOutTime" in candidates.columns:
        candidates = candidates[candidates["PitOutTime"].isna()]
    if "LapTime" not in candidates.columns or candidates.empty:
        return candidates.iloc[0:0]
    return candidates.dropna(subset=["LapTime"]).sort_values("LapTime")


def _clean_lap_windows(laps: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """Per-driver session-time spans of laps with no pit in/out, sorted by time."""
    windows: dict[str, list[tuple[float, float]]] = {}
    clean = _clean_lap_candidates(laps)
    if clean.empty or "Driver" not in clean.columns:
        return windows
    for _, lap in clean.iterrows():
        start = _td_seconds(lap.get("LapStartTime"))
        lap_time = _td_seconds(lap.get("LapTime"))
        if start is None or not lap_time:
            continue
        code = str(lap.get("Driver") or "").strip()
        if not code:
            continue
        windows.setdefault(code, []).append((start, start + lap_time))
    for spans in windows.values():
        spans.sort()
    return windows


def _raw_pos_traces(session) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Per-driver-code (time, x, y) from the raw position feed, cleaned."""
    pos_data = getattr(session, "pos_data", None) or {}
    num_to_code: dict[str, str] = {}
    results = getattr(session, "results", None)
    if results is not None and len(results) > 0:
        for _, row in results.iterrows():
            num = str(row.get("DriverNumber") or "").strip()
            code = str(row.get("Abbreviation") or "").strip()
            if num and code:
                num_to_code[num] = code

    traces: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for num, df in pos_data.items():
        code = num_to_code.get(str(num))
        if code is None or df is None or len(df) == 0 or "X" not in getattr(df, "columns", []):
            continue
        x = df["X"].to_numpy(dtype=float)
        y = df["Y"].to_numpy(dtype=float)
        t = df["SessionTime"].map(_td_seconds).to_numpy(dtype=float)
        mask = (
            np.isfinite(x)
            & np.isfinite(y)
            & np.isfinite(t)
            & ~((np.abs(x) < 1e-3) & (np.abs(y) < 1e-3))
        )
        if mask.sum() < 100:
            continue
        t, x, y = t[mask], x[mask], y[mask]
        order = np.argsort(t)
        traces[code] = (t[order], x[order], y[order])
    return traces


def _self_parallel_fraction(x: np.ndarray, y: np.ndarray) -> float:
    """Fraction of points running alongside a far-away part of the same path.

    A single clean lap is ~0. A path that covers the circuit twice, or that
    detours down a pit lane parallel to the main straight, scores high.
    """
    n = len(x)
    if n < 60:
        return 0.0
    extent = max(x.max() - x.min(), y.max() - y.min())
    if extent <= 0:
        return 0.0
    pts = np.column_stack([x, y])
    min_sep = max(20, n // 8)
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(pts)
        neighbours = tree.query_ball_point(pts, extent * 0.008)
    except Exception:
        return 0.0
    flagged = 0
    for i, nb in enumerate(neighbours):
        for j in nb:
            if min(abs(i - j), n - abs(i - j)) > min_sep:
                flagged += 1
                break
    return flagged / n


def _extract_loop(
    t: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    windows: list[tuple[float, float]],
) -> tuple[int, np.ndarray, np.ndarray] | None:
    """Find exactly one densely-sampled racing lap in a continuous trace.

    Lap timing metadata does not always line up with the position feed (at
    Hungary 2026 a lap-timed slice starts and ends a third of the circuit
    apart), so the lap is found geometrically: walk the trace until the car
    returns to where it started.

    Two constraints keep the result honest. The walk may only cross samples
    inside `windows` (clean laps with no pit in/out), so a pit-lane detour can
    never end up in the racing line. And the cut is made at the first local
    minimum of distance-to-start rather than the first sample inside a fixed
    tolerance: a slightly different racing line through the start point used to
    miss that tolerance entirely and run on for a second lap, which is what
    doubled the outline on 7 of 11 circuits.
    """
    if len(x) < 200 or not windows:
        return None
    extent = max(x.max() - x.min(), y.max() - y.min())
    if extent <= 0:
        return None

    allowed = np.zeros(len(t), dtype=bool)
    for w_start, w_end in windows:
        lo = int(np.searchsorted(t, w_start, side="left"))
        hi = int(np.searchsorted(t, w_end, side="right"))
        allowed[lo:hi] = True
    if allowed.sum() < 200:
        return None

    step = np.hypot(np.diff(x), np.diff(y))
    cum = np.concatenate([[0.0], np.cumsum(step)])
    max_step = extent * 0.06
    min_travel = extent * 2.0
    max_travel = extent * 12.0
    tol_return = extent * 0.05

    candidates = np.flatnonzero(allowed)
    starts = candidates[np.linspace(0, len(candidates) - 1, 120).astype(int)]
    tight_close = extent * 0.015  # roughly one sample of travel

    best: tuple[int, np.ndarray, np.ndarray] | None = None
    best_key: tuple[int, float] | None = None
    for start in starts:
        start = int(start)
        j = start + 1
        prev_dist = math.inf
        cut = None
        while j < len(x):
            if not allowed[j] or step[j - 1] > max_step:
                break  # left a clean lap, or hit a feed dropout
            travel = cum[j] - cum[start]
            if travel > max_travel:
                break
            if travel > min_travel:
                dist = math.hypot(x[j] - x[start], y[j] - y[start])
                if dist > prev_dist and prev_dist <= tol_return:
                    cut = j - 1  # closest approach was the previous sample
                    break
                prev_dist = dist
            j += 1
        if cut is None:
            continue
        n = cut - start + 1
        # Rank a well-closed loop above a sample-rich one. Preferring raw point
        # count alone favours loops that run past the start/finish line, which
        # left the Hungaroring centerline 3% longer than the real circuit and
        # made arc-length progress unreliable there.
        closes = 1 if prev_dist <= tight_close else 0
        key = (closes, float(n))
        if best_key is not None and key <= best_key:
            continue
        lx, ly = x[start : cut + 1], y[start : cut + 1]
        if _self_parallel_fraction(lx, ly) > 0.10:
            continue  # still covers the circuit more than once
        best, best_key = (n, lx, ly), key
    return best


def _pit_windows(laps: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """Per-driver session-time spans spent in the pit lane.

    From pit entry (`PitInTime`) to pit exit (`PitOutTime` of the following lap).
    This comes from timing rather than geometry, so it is reliable at every
    circuit even where the position feed is too coarse to draw a pit lane.
    """
    windows: dict[str, list[tuple[float, float]]] = {}
    if laps is None or laps.empty or "Driver" not in laps.columns:
        return windows
    if "PitInTime" not in laps.columns or "PitOutTime" not in laps.columns:
        return windows
    for code, dl in laps.groupby("Driver"):
        rows = list(dl.sort_values("LapNumber").itertuples())
        spans: list[tuple[float, float]] = []
        for i, row in enumerate(rows):
            t_in = _td_seconds(getattr(row, "PitInTime", None))
            if t_in is None or i + 1 >= len(rows):
                continue
            t_out = _td_seconds(getattr(rows[i + 1], "PitOutTime", None))
            if t_out is None or t_out <= t_in:
                continue
            spans.append((t_in, t_out))
        if spans:
            windows[str(code)] = spans
    return windows


def _build_pitlane(
    traces: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    pit_windows: dict[str, list[tuple[float, float]]],
    rotation: float,
    track_x: np.ndarray,
    track_y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Derive the pit-lane path from cars actually driving through it.

    Returns None when the position feed is too coarse to produce a coherent
    path — at Hungary 2026 a single stop jumps ~420 m between samples, so there
    is nothing trustworthy to draw and the caller falls back to marking pitting
    cars instead of inventing geometry.
    """
    extent = max(track_x.max() - track_x.min(), track_y.max() - track_y.min())
    if extent <= 0:
        return None
    max_step = extent * 0.03

    best: tuple[int, np.ndarray, np.ndarray] | None = None
    for code, spans in pit_windows.items():
        trace = traces.get(code)
        if trace is None:
            continue
        t_all, x_all, y_all = trace
        for t_in, t_out in spans:
            lo = int(np.searchsorted(t_all, t_in, side="left"))
            hi = int(np.searchsorted(t_all, t_out, side="right"))
            if hi - lo < 20:
                continue
            px, py = _rotate_xy(x_all[lo:hi], y_all[lo:hi], rotation)
            px, py = _dedupe_consecutive(px, py)
            if len(px) < 40:
                continue
            step = np.hypot(np.diff(px), np.diff(py))
            if step.max() > max_step:
                continue  # feed dropout mid-stop
            length = float(step.sum())
            if not (extent * 0.15 <= length <= extent * 1.5):
                continue  # too short to be the pit lane, or a whole lap
            if best is None or len(px) > best[0]:
                best = (len(px), px, py)

    if best is None:
        return None

    _n, px, py = best
    # The pit lane must actually sit away from the racing line, otherwise we
    # would draw a second stripe on top of the track.
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(np.column_stack([track_x, track_y]))
        dist, _idx = tree.query(np.column_stack([px, py]), k=1)
        if float(np.percentile(dist, 75)) < extent * 0.004:
            logger.debug("Pit lane indistinguishable from racing line — skipping")
            return None
    except Exception:
        pass
    return px, py


def _build_centerline(session, laps: pd.DataFrame) -> tuple[np.ndarray, np.ndarray] | None:
    """Stack many clean laps, binned by lap fraction, into one dense centerline.

    Laps are chosen by how many *distinct* positions the feed reported during
    them, not by lap time. The feed can decimate badly for stretches of a session
    (at Hungary 2026 it drops to ~2.5 s updates late on, exactly where the fastest
    laps are), so the quickest lap is often the worst-sampled one. Candidates are
    still capped near the fastest lap time, because binning by lap fraction
    assumes every stacked lap is run at a comparable pace.
    """
    if laps is None or laps.empty:
        return None
    timed = _clean_lap_candidates(laps)
    if timed.empty:
        return None
    traces = _raw_pos_traces(session)
    if not traces:
        return None

    # Preferred: one clean, densely-sampled loop straight from the raw trace
    clean_windows = _clean_lap_windows(laps)
    best_loop: tuple[int, np.ndarray, np.ndarray] | None = None
    for code, (tt, tx, ty) in traces.items():
        windows = clean_windows.get(code)
        if not windows:
            continue
        keep = np.concatenate([[True], (np.diff(tx) != 0) | (np.diff(ty) != 0)])
        loop = _extract_loop(tt[keep], tx[keep], ty[keep], windows)
        if loop is not None and (best_loop is None or loop[0] > best_loop[0]):
            best_loop = loop
    if best_loop is not None and best_loop[0] >= SINGLE_LAP_MIN_POINTS:
        logger.debug("Centerline from raw-trace loop (%d points)", best_loop[0])
        return best_loop[1], best_loop[2]

    fastest = _td_seconds(timed.iloc[0].get("LapTime"))
    max_lap_time = fastest * 1.06 if fastest else None

    scored: list[tuple[int, np.ndarray, np.ndarray, np.ndarray]] = []
    for _, lap in timed.iterrows():
        lap_start = _td_seconds(lap.get("LapStartTime"))
        lap_time = _td_seconds(lap.get("LapTime"))
        if lap_start is None or not lap_time:
            continue
        if max_lap_time is not None and lap_time > max_lap_time:
            break  # candidates are sorted by lap time
        trace = traces.get(str(lap.get("Driver") or ""))
        if trace is None:
            continue
        t_all, x_all_d, y_all_d = trace
        lo = int(np.searchsorted(t_all, lap_start, side="left"))
        hi = int(np.searchsorted(t_all, lap_start + lap_time, side="right"))
        if hi - lo < 60:
            continue
        t = t_all[lo:hi]
        x = x_all_d[lo:hi]
        y = y_all_d[lo:hi]

        # Held/stale coordinates would drag each bin's median backwards
        keep = np.concatenate([[True], (np.diff(x) != 0) | (np.diff(y) != 0)])
        t, x, y = t[keep], x[keep], y[keep]
        u = (t - lap_start) / lap_time
        inside = (u >= 0.0) & (u <= 1.0)
        if inside.sum() < 120:
            continue
        scored.append((int(inside.sum()), u[inside], x[inside], y[inside]))

    if not scored:
        return None
    scored.sort(key=lambda s: -s[0])

    # A single well-sampled lap gives a crisper line than a stack, because
    # stacking mixes laps run at slightly different paces and smears the bins.
    best_n, _bu, bx_one, by_one = scored[0]
    if best_n >= SINGLE_LAP_MIN_POINTS:
        extent = max(bx_one.max() - bx_one.min(), by_one.max() - by_one.min())
        closure = math.hypot(bx_one[0] - bx_one[-1], by_one[0] - by_one[-1])
        if extent > 0 and closure / extent <= 0.08:
            logger.debug("Centerline from single lap (%d points)", best_n)
            return bx_one, by_one

    chosen = scored[:MAX_CENTERLINE_LAPS]
    used = len(chosen)
    us = [c[1] for c in chosen]
    xs = [c[2] for c in chosen]
    ys = [c[3] for c in chosen]

    u_all = np.concatenate(us)
    x_all = np.concatenate(xs)
    y_all = np.concatenate(ys)

    n_bins = CENTERLINE_POINTS
    bin_idx = np.clip((u_all * n_bins).astype(int), 0, n_bins - 1)
    bx = np.full(n_bins, np.nan)
    by = np.full(n_bins, np.nan)
    order = np.argsort(bin_idx, kind="stable")
    bin_sorted = bin_idx[order]
    starts = np.searchsorted(bin_sorted, np.arange(n_bins), side="left")
    ends = np.searchsorted(bin_sorted, np.arange(n_bins), side="right")
    xs_sorted = x_all[order]
    ys_sorted = y_all[order]
    for b in range(n_bins):
        lo, hi = starts[b], ends[b]
        if hi > lo:
            bx[b] = np.median(xs_sorted[lo:hi])
            by[b] = np.median(ys_sorted[lo:hi])

    filled = np.isfinite(bx)
    if filled.sum() < 40:
        logger.debug("Centerline stack too sparse (%d bins)", int(filled.sum()))
        return None
    if not filled.all():
        # Wrap-around interpolation across empty bins
        idx = np.arange(n_bins)
        known = idx[filled]
        ext_known = np.concatenate([known - n_bins, known, known + n_bins])
        ext_bx = np.concatenate([bx[filled], bx[filled], bx[filled]])
        ext_by = np.concatenate([by[filled], by[filled], by[filled]])
        bx = np.interp(idx, ext_known, ext_bx)
        by = np.interp(idx, ext_known, ext_by)

    logger.debug("Centerline from %d laps, %d filled bins", used, int(filled.sum()))
    return bx, by


def _pick_centerline_lap(session, laps: pd.DataFrame) -> tuple[np.ndarray, np.ndarray] | None:
    """Fallback: the densest single clean lap that forms a closed loop."""
    if laps is None or laps.empty:
        return None
    timed = _clean_lap_candidates(laps)
    best: tuple[int, np.ndarray, np.ndarray] | None = None
    scanned = 0
    for _, lap in timed.iterrows():
        if scanned >= 250:
            break
        scanned += 1
        try:
            tel = lap.get_pos_data()
        except Exception:
            continue
        if tel is None or "X" not in getattr(tel, "columns", []) or len(tel) < 50:
            continue
        x = tel["X"].to_numpy(dtype=float)
        y = tel["Y"].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y) & ~((np.abs(x) < 1e-3) & (np.abs(y) < 1e-3))
        if mask.sum() < 50:
            continue
        dx, dy = _dedupe_consecutive(x[mask], y[mask])
        if len(dx) < 60:
            continue
        extent = max(dx.max() - dx.min(), dy.max() - dy.min())
        if extent <= 0:
            continue
        closure = math.hypot(dx[0] - dx[-1], dy[0] - dy[-1]) / extent
        if closure > 0.08:
            continue
        if best is None or len(dx) > best[0]:
            best = (len(dx), dx, dy)
        if best[0] >= 300:
            break
    if best is not None:
        return best[1], best[2]

    pos_data = getattr(session, "pos_data", None) or {}
    for _drv, df in pos_data.items():
        if df is None or len(df) < 50 or "X" not in getattr(df, "columns", []):
            continue
        x = df["X"].to_numpy(dtype=float)
        y = df["Y"].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y) & ~((np.abs(x) < 1e-3) & (np.abs(y) < 1e-3))
        dx, dy = _dedupe_consecutive(x[mask], y[mask])
        if len(dx) < 60:
            continue
        return dx[:2000], dy[:2000]
    return None


def _driver_meta(
    session,
    laps: pd.DataFrame,
    t0: float,
    duration_s: int,
) -> list[dict[str, Any]]:
    results = getattr(session, "results", None)
    drivers: list[dict[str, Any]] = []
    if results is None or len(results) == 0:
        return drivers

    # When each car was last actually racing — the reliable DNF signal. Status
    # text alone is not enough (e.g. Stroll AUS 2026 is "Lapped" but classified R).
    last_seen: dict[str, float] = {}
    if laps is not None and not laps.empty and "Driver" in laps.columns:
        for code, dl in laps.groupby("Driver"):
            ends: list[float] = []
            for _, row in dl.iterrows():
                start = _td_seconds(row.get("LapStartTime"))
                lap_t = _td_seconds(row.get("LapTime"))
                if start is None:
                    continue
                ends.append(start + lap_t if lap_t is not None else start)
            if ends:
                last_seen[str(code)] = max(ends) - t0

    for _, row in results.iterrows():
        code = str(row.get("Abbreviation") or "").strip()
        if not code:
            continue
        team = str(row.get("TeamName") or row.get("Team") or "").strip()
        try:
            number = int(str(row.get("DriverNumber") or 0).strip() or 0)
        except (TypeError, ValueError):
            number = 0

        status = str(row.get("Status") or "").strip()
        classified = str(row.get("ClassifiedPosition") or "").strip()
        finished = classified not in {"R", "W", "D", "E", "N", "F"} and status in {
            "Finished",
            "Lapped",
        }
        started = status != "Did not start" and classified != "W"
        end_t = last_seen.get(code)
        if not started:
            end_t = 0.0
        elif finished or end_t is None:
            # Keep classified finishers on track through the chequered flag
            end_t = float(duration_s)
        end_t = float(min(max(end_t, 0.0), float(duration_s)))

        try:
            finish_pos = int(row.get("Position")) if not pd.isna(row.get("Position")) else None
        except (TypeError, ValueError):
            finish_pos = None
        try:
            grid = int(row.get("GridPosition")) if not pd.isna(row.get("GridPosition")) else None
        except (TypeError, ValueError):
            grid = None

        drivers.append(
            {
                "code": code,
                "name": str(row.get("FullName") or row.get("BroadcastName") or code),
                "team": team,
                "number": number,
                "color": get_team_color(team),
                "status": status,
                "classified": classified,
                "finished": bool(finished),
                "started": bool(started),
                "finish_position": finish_pos,
                "grid": grid,
                "end_t_s": round(end_t, 1),
            }
        )
    drivers.sort(key=lambda d: (d["number"] or 99, d["code"]))
    return drivers


def _make_offtrack_filter(track_x: np.ndarray, track_y: np.ndarray):
    """Reject GPS spikes that place a car implausibly far from the circuit.

    Pit lanes run alongside the track so they stay within tolerance; wild
    outliers (e.g. one stray sample in China 2026) get dropped.
    """
    extent = max(track_x.max() - track_x.min(), track_y.max() - track_y.min())
    tol = extent * 0.06
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(np.column_stack([track_x, track_y]))

        def near(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            dist, _ = tree.query(np.column_stack([x, y]), k=1)
            return dist <= tol

        return near
    except Exception:
        # Bounding-box fallback keeps the build working without scipy
        min_x, max_x = track_x.min() - tol, track_x.max() + tol
        min_y, max_y = track_y.min() - tol, track_y.max() + tol

        def near_box(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            return (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)

        return near_box


def _build_positions(
    session,
    drivers: list[dict[str, Any]],
    t0: float,
    duration_s: int,
    proj: Projection,
    rotation: float,
    on_track=None,
) -> tuple[
    dict[str, dict[str, list[int]]],
    dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
]:
    """Resample each car's GPS to 1 Hz from t0..t0+duration, quantized.

    Also returns, per driver, the pre-quantization world coordinates and the
    feed gap each frame was interpolated across, so the running order can be
    derived by projecting onto the centerline without touching the feed again —
    and can tell how much that projection is worth.
    """
    pos_data = getattr(session, "pos_data", None) or {}
    # FastF1 uses string DriverNumber keys in pos_data / results.
    num_to_code: dict[str, str] = {}
    results = getattr(session, "results", None)
    if results is not None and len(results) > 0:
        for _, row in results.iterrows():
            num = str(row.get("DriverNumber") or "").strip()
            code = str(row.get("Abbreviation") or "").strip()
            if num and code:
                num_to_code[num] = code

    code_to_num = {c: n for n, c in num_to_code.items()}
    n_frames = duration_s * HZ + 1
    target_t = np.arange(n_frames, dtype=float) / HZ  # seconds from t0

    out: dict[str, dict[str, list[int]]] = {}
    world: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    missing = np.full(n_frames, np.nan)
    for drv in drivers:
        code = drv["code"]
        # Never draw a car after it retired
        end_t = float(drv.get("end_t_s") or duration_s)
        num = code_to_num.get(code)
        df = None
        if num is not None:
            df = pos_data.get(num)
            if df is None:
                # Fall back to int-keyed dicts from older FastF1 caches
                try:
                    df = pos_data.get(int(num))
                except (TypeError, ValueError):
                    df = None
        if df is None or len(df) == 0:
            out[code] = {"x": [-1] * n_frames, "y": [-1] * n_frames}
            world[code] = (missing.copy(), missing.copy(), missing.copy())
            continue

        times = df["SessionTime"].map(_td_seconds).to_numpy(dtype=float) - t0
        x_raw = df["X"].to_numpy(dtype=float)
        y_raw = df["Y"].to_numpy(dtype=float)
        status = df["Status"].to_numpy() if "Status" in df.columns else None

        valid = np.isfinite(times) & np.isfinite(x_raw) & np.isfinite(y_raw)
        # GPS feed often parks cars at the origin when off-track / unavailable
        valid &= ~((np.abs(x_raw) < 1e-3) & (np.abs(y_raw) < 1e-3))
        if status is not None and status.dtype.kind in ("U", "O", "S"):
            st = status.astype(str)
            valid &= ~np.isin(st, ["Garage", "OutOfRace", "Retired"])
        times = times[valid]
        x_raw = x_raw[valid]
        y_raw = y_raw[valid]
        if len(times) < 2:
            out[code] = {"x": [-1] * n_frames, "y": [-1] * n_frames}
            world[code] = (missing.copy(), missing.copy(), missing.copy())
            continue

        order = np.argsort(times)
        times = times[order]
        x_raw = x_raw[order]
        y_raw = y_raw[order]
        xr, yr = _rotate_xy(x_raw, y_raw, rotation)

        if on_track is not None and len(xr):
            keep = on_track(xr, yr)
            if keep.sum() >= 2:
                times, xr, yr = times[keep], xr[keep], yr[keep]

        # Interpolate; mark gaps > 3s as missing
        x_i = np.interp(target_t, times, xr, left=np.nan, right=np.nan)
        y_i = np.interp(target_t, times, yr, left=np.nan, right=np.nan)
        idx = np.searchsorted(times, target_t, side="left")
        idx = np.clip(idx, 1, len(times) - 1)
        gap = times[idx] - times[idx - 1]
        near = (
            (target_t >= times[0] - 0.5)
            & (target_t <= times[-1] + 0.5)
            & (gap <= 3.0)
            & (target_t <= end_t + 1.0)
        )
        x_i = np.where(near, x_i, np.nan)
        y_i = np.where(near, y_i, np.nan)

        qx, qy = proj.apply(np.nan_to_num(x_i, nan=0.0), np.nan_to_num(y_i, nan=0.0))
        qx = np.where(np.isfinite(x_i), qx, -1).astype(int)
        qy = np.where(np.isfinite(y_i), qy, -1).astype(int)
        out[code] = {"x": qx.tolist(), "y": qy.tolist()}
        world[code] = (x_i, y_i, gap)
    return out, world


def _time_progress(
    laps: pd.DataFrame,
    drivers: list[dict[str, Any]],
    t0: float,
    duration_s: int,
) -> dict[str, np.ndarray]:
    """Lap progress interpolated linearly in time between lap crossings.

    Exact at every crossing but only an approximation in between, so it serves
    as the fallback wherever GPS is unavailable (e.g. Monaco 2026).
    """
    n_frames = duration_s * HZ + 1
    target_t = np.arange(n_frames, dtype=float) / HZ
    out: dict[str, np.ndarray] = {}
    if laps is None or laps.empty or "Driver" not in laps.columns:
        return out

    by_driver = {str(code): dl for code, dl in laps.groupby("Driver")}
    for drv in drivers:
        code = drv["code"]
        dl = by_driver.get(code)
        if dl is None or dl.empty:
            out[code] = np.full(n_frames, np.nan)
            continue

        dl = dl.sort_values("LapNumber")
        knot_t: list[float] = []
        knot_lap: list[float] = []
        for _, row in dl.iterrows():
            start = _td_seconds(row.get("LapStartTime"))
            try:
                lap_n = float(row.get("LapNumber"))
            except (TypeError, ValueError):
                continue
            if start is None:
                continue
            knot_t.append(start - t0)
            knot_lap.append(lap_n - 1.0)
        if len(knot_t) < 2:
            out[code] = np.full(n_frames, np.nan)
            continue

        # Extend past the final lap start so the last lap interpolates too
        last = dl.iloc[-1]
        last_start = _td_seconds(last.get("LapStartTime"))
        last_time = _td_seconds(last.get("LapTime"))
        if last_start is not None:
            span = last_time if last_time is not None else float(np.median(np.diff(knot_t)))
            knot_t.append(last_start - t0 + (span or 90.0))
            knot_lap.append(float(last.get("LapNumber") or 0))

        kt = np.asarray(knot_t, dtype=float)
        kl = np.asarray(knot_lap, dtype=float)
        order = np.argsort(kt)
        out[code] = np.interp(target_t, kt[order], kl[order], left=np.nan, right=np.nan)
    return out


def _lap_crossings(laps: pd.DataFrame, t0: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per-driver (crossing time relative to t0, lap number starting that lap)."""
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if laps is None or laps.empty or "Driver" not in laps.columns:
        return out
    for code, dl in laps.groupby("Driver"):
        times: list[float] = []
        nums: list[float] = []
        for _, row in dl.sort_values("LapNumber").iterrows():
            start = _td_seconds(row.get("LapStartTime"))
            try:
                lap_n = float(row.get("LapNumber"))
            except (TypeError, ValueError):
                continue
            if start is None:
                continue
            times.append(start - t0)
            nums.append(lap_n)
        if times:
            order = np.argsort(np.asarray(times))
            out[str(code)] = (np.asarray(times)[order], np.asarray(nums)[order])
    return out


def _build_progress(
    laps: pd.DataFrame,
    drivers: list[dict[str, Any]],
    world: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    center_x: np.ndarray,
    center_y: np.ndarray,
    t0: float,
    duration_s: int,
) -> tuple[dict[str, list[int]], dict[str, float]]:
    """Per-frame race progress in thousandths of a lap, for live running order.

    Each car's position is projected onto the arc-length-resampled centerline to
    get how far round the lap it actually is — that fraction is what makes the
    order agree with what the track map shows. Geometry alone cannot say *which*
    lap, so the lap integer is taken from the timing-interpolated progress, which
    is exact at every crossing: `progress = round(time_prog - frac) + frac`.

    The two sources are then blended rather than one replacing the other, because
    they are accurate in different places. Timing is exact at a lap crossing but
    assumes constant pace in between; geometry is the reverse, carrying ~1 s of
    feed quantization but knowing exactly where on the lap a car sits. The weight
    therefore falls to zero at each crossing and saturates across the rest of the
    lap. Measured against `laps.Position`, geometry alone scored 90.9% and timing
    alone 94.8% at crossings; the blend keeps the crossing accuracy while still
    ordering mid-lap traffic by real track position.

    Time interpolation also fills any frame without usable GPS.

    Returns the progress scaled by PROG_SCALE plus the fraction of frames that
    came from geometry per driver, for logging.
    """
    n_frames = duration_s * HZ + 1
    fallback = _time_progress(laps, drivers, t0, duration_s)
    crossings = _lap_crossings(laps, t0)
    out: dict[str, list[int]] = {}
    geom_share: dict[str, float] = {}

    tree = None
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(np.column_stack([center_x, center_y]))
    except Exception as exc:
        logger.warning("scipy unavailable, progress falls back to lap timing: %s", exc)

    n_center = len(center_x)
    # Where the start/finish line sits on the centerline: the centerline starts
    # wherever the extracted lap happened to begin, not at the line.
    sf_index = 0.0
    if tree is not None:
        anchors_x: list[float] = []
        anchors_y: list[float] = []
        for drv in drivers:
            wx, wy, _g = world.get(drv["code"], (None, None, None))
            cross = crossings.get(drv["code"])
            if wx is None or cross is None:
                continue
            for t_cross in cross[0]:
                fi = int(round(t_cross * HZ))
                if 0 <= fi < n_frames and np.isfinite(wx[fi]):
                    anchors_x.append(float(wx[fi]))
                    anchors_y.append(float(wy[fi]))
        if len(anchors_x) >= 5:
            _d, idx = tree.query(np.column_stack([anchors_x, anchors_y]), k=1)
            # Circular mean: the crossings should all land on the same point
            ang = idx / n_center * 2 * math.pi
            mean_ang = math.atan2(float(np.mean(np.sin(ang))), float(np.mean(np.cos(ang))))
            sf_index = (mean_ang / (2 * math.pi)) * n_center % n_center
            logger.debug("Start/finish at centerline index %.0f/%d", sf_index, n_center)

            # How well does lap timing agree with the position feed? Each lap
            # crossing should project onto the start/finish line. At Hungary 2026
            # it scatters by up to a third of a lap, meaning the two feeds are not
            # aligned there, and arc-length progress would order cars by GPS while
            # the lap count came from timing. Better to use timing for everything.
            resid = ((idx - sf_index) % n_center) / n_center
            resid = np.where(resid > 0.5, resid - 1.0, resid)
            spread = float(np.percentile(np.abs(resid), 90))
            if spread > GEOM_ALIGN_TOL:
                logger.warning(
                    "Lap timing and position feed disagree by %.1f%% of a lap — "
                    "using lap timing alone for running order",
                    100 * spread,
                )
                tree = None
            else:
                logger.debug("Timing/feed alignment %.2f%% of a lap", 100 * spread)

    for drv in drivers:
        code = drv["code"]
        end_t = float(drv.get("end_t_s") or duration_s)
        base = fallback.get(code)
        if base is None:
            base = np.full(n_frames, np.nan)
        prog = base.copy()
        share = 0.0

        wx, wy, gap = world.get(code, (None, None, None))
        if tree is not None and wx is not None and np.isfinite(base).any():
            # Only trust geometry where the feed is dense. Interpolating a 2.5 s
            # gap (Hungary 2026) moves a car ~140 m, which is worse than assuming
            # constant pace, so those frames stay on lap timing.
            usable = (
                np.isfinite(wx)
                & np.isfinite(wy)
                & np.isfinite(base)
                & (np.nan_to_num(gap, nan=9.0) <= MAX_GEOM_FEED_GAP_S)
            )
            if usable.sum() >= 10:
                _dist, idx = tree.query(
                    np.column_stack([np.where(usable, wx, 0.0), np.where(usable, wy, 0.0)]), k=1
                )
                frac = ((idx - sf_index) % n_center) / n_center
                # Snap to whichever lap puts geometry closest to the timing
                # estimate; timing is exact at crossings so it never picks wrong.
                safe_base = np.where(usable, base, 0.0)
                geom = np.round(safe_base - frac) + frac
                weight = np.clip(
                    np.sin(np.pi * np.mod(safe_base, 1.0)) / GEOM_WEIGHT_RAMP, 0.0, 1.0
                )
                blended = safe_base + weight * (geom - safe_base)
                prog = np.where(usable, blended, prog)
                share = float(usable.mean())

        # Cars only ever move forwards
        finite = np.isfinite(prog)
        if finite.any():
            vals = prog[finite]
            prog[finite] = np.maximum.accumulate(vals)
        prog = np.where(np.arange(n_frames) / HZ <= end_t + 1.0, prog, np.nan)
        out[code] = (
            np.where(np.isfinite(prog), np.round(prog * PROG_SCALE), -1).astype(int).tolist()
        )
        geom_share[code] = share
    return out, geom_share


def _build_feed(session, t0: float, duration_s: int) -> list[dict[str, Any]]:
    """Race control messages mapped onto race-relative seconds."""
    rcm = getattr(session, "race_control_messages", None)
    if rcm is None or len(rcm) == 0:
        return []

    t0_date = getattr(session, "t0_date", None)
    entries: list[dict[str, Any]] = []
    for _, row in rcm.iterrows():
        raw_time = row.get("Time")
        t_s: float | None = None
        if isinstance(raw_time, pd.Timedelta):
            t_s = _td_seconds(raw_time)
        elif raw_time is not None and not pd.isna(raw_time) and t0_date is not None:
            try:
                t_s = float((pd.Timestamp(raw_time) - pd.Timestamp(t0_date)).total_seconds())
            except (TypeError, ValueError):
                t_s = None
        if t_s is None:
            continue
        rel = t_s - t0
        if rel < -60 or rel > duration_s + 120:
            continue

        flag = str(row.get("Flag") or "").strip().upper()
        if flag in FEED_SKIP_FLAGS:
            continue
        message = str(row.get("Message") or "").strip()
        if not message:
            continue

        try:
            lap = int(row.get("Lap")) if not pd.isna(row.get("Lap")) else None
        except (TypeError, ValueError):
            lap = None

        entries.append(
            {
                "t_s": round(max(0.0, rel), 1),
                "category": str(row.get("Category") or "").strip(),
                "flag": flag,
                "scope": str(row.get("Scope") or "").strip(),
                "lap": lap,
                "message": message,
            }
        )
    entries.sort(key=lambda e: e["t_s"])
    return entries


def _build_stints_and_pits(
    laps: pd.DataFrame, t0: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stints: list[dict[str, Any]] = []
    pits: list[dict[str, Any]] = []
    if laps is None or laps.empty:
        return stints, pits

    code_col = "Driver" if "Driver" in laps.columns else None
    if code_col is None:
        return stints, pits

    for code, dl in laps.groupby(code_col):
        code_s = str(code)
        if "Stint" not in dl.columns:
            continue
        for stint_id, sl in dl.groupby("Stint"):
            if pd.isna(stint_id):
                continue
            sl = sl.sort_values("LapNumber")
            compound = str(sl["Compound"].dropna().iloc[0]) if "Compound" in sl.columns and sl["Compound"].notna().any() else "UNKNOWN"
            start_lap = int(sl["LapNumber"].min())
            end_lap = int(sl["LapNumber"].max())
            t_start = _td_seconds(sl.iloc[0].get("LapStartTime"))
            # End at pit-in of last lap in stint, else estimate from next lap start / lap time
            last = sl.iloc[-1]
            t_end = _td_seconds(last.get("PitInTime"))
            if t_end is None:
                t_end = _td_seconds(last.get("LapStartTime"))
                lt = _td_seconds(last.get("LapTime"))
                if t_end is not None and lt is not None:
                    t_end = t_end + lt
            if t_start is None:
                continue
            stints.append(
                {
                    "code": code_s,
                    "stint": int(stint_id),
                    "compound": compound.upper(),
                    "start_lap": start_lap,
                    "end_lap": end_lap,
                    "t_start_s": round(t_start - t0, 1),
                    "t_end_s": round((t_end - t0) if t_end is not None else t_start - t0, 1),
                }
            )

        pit_rows = dl[dl["PitInTime"].notna()] if "PitInTime" in dl.columns else dl.iloc[0:0]
        for _, row in pit_rows.iterrows():
            t = _td_seconds(row.get("PitInTime"))
            if t is None:
                continue
            try:
                lap_n = int(row.get("LapNumber") or 0)
            except (TypeError, ValueError):
                lap_n = 0
            pits.append({"code": code_s, "t_s": round(t - t0, 1), "lap": lap_n})

    stints.sort(key=lambda s: (s["code"], s["stint"]))
    pits.sort(key=lambda p: (p["t_s"], p["code"]))
    return stints, pits


def _session_abort_restarts(
    session_status: pd.DataFrame | None, t0: float
) -> list[tuple[float, float]]:
    """(abort, restart) race-relative times from session status Aborted → Started."""
    if session_status is None or len(session_status) == 0:
        return []
    rows: list[tuple[float, str]] = []
    for _, row in session_status.iterrows():
        t = _td_seconds(row.get("Time"))
        if t is None:
            continue
        status = str(row.get("Status") or "").strip()
        if status:
            rows.append((t - t0, status))
    rows.sort(key=lambda r: r[0])

    pairs: list[tuple[float, float]] = []
    i = 0
    while i < len(rows):
        t_abort, status = rows[i]
        if status != "Aborted":
            i += 1
            continue
        restart: float | None = None
        for j in range(i + 1, len(rows)):
            t_next, st = rows[j]
            if st == "Started":
                restart = t_next
                break
        if restart is not None and restart > t_abort:
            pairs.append((t_abort, restart))
        i += 1
    return pairs


def _build_flags(
    track_status: pd.DataFrame | None,
    t0: float,
    duration_s: int,
    session_status: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    if track_status is None or len(track_status) == 0:
        return []
    rows = []
    for _, row in track_status.iterrows():
        t = _td_seconds(row.get("Time"))
        if t is None:
            continue
        status = str(row.get("Status") or "").strip()
        rows.append((t - t0, status))
    rows.sort(key=lambda r: r[0])
    if not rows:
        return []

    # Red-flag track status often clears while cars are still waiting in pit lane.
    # Session Aborted→Started covers that suspended period through the restart.
    red_restarts = _session_abort_restarts(session_status, t0)

    flags: list[dict[str, Any]] = []
    i = 0
    while i < len(rows):
        t_start, status = rows[i]
        kind = None
        if status in STATUS_SC:
            kind = "SC"
        elif status in STATUS_VSC:
            kind = "VSC"
        elif status in STATUS_RED:
            kind = "RED"
        if kind is None:
            i += 1
            continue
        j = i + 1
        while j < len(rows):
            _, st = rows[j]
            if kind == "SC" and st in STATUS_SC:
                j += 1
                continue
            if kind == "VSC" and st in STATUS_VSC:
                j += 1
                continue
            if kind == "RED" and st in STATUS_RED:
                j += 1
                continue
            break
        t_end = rows[j][0] if j < len(rows) else float(duration_s)
        if kind == "RED" and red_restarts:
            for abort_t, restart_t in red_restarts:
                # Match this red window to the abort/restart that covers it.
                if abort_t <= t_end + 5.0 and restart_t > t_start:
                    t_end = max(t_end, restart_t)
                    break
        # Skip windows entirely before lights out or after race end
        if t_end > 0 and t_start < duration_s:
            flags.append(
                {
                    "type": kind,
                    "t_start_s": round(max(0.0, t_start), 1),
                    "t_end_s": round(min(float(duration_s), t_end), 1),
                }
            )
        i = j if j > i else i + 1
    return flags


def _build_lap_markers(laps: pd.DataFrame, t0: float) -> list[dict[str, Any]]:
    """Leader lap-start times for scrubber ticks."""
    if laps is None or laps.empty or "Position" not in laps.columns:
        return []
    leader = laps[laps["Position"] == 1].sort_values("LapNumber")
    markers: list[dict[str, Any]] = []
    seen: set[int] = set()
    for _, row in leader.iterrows():
        try:
            lap_n = int(row["LapNumber"])
        except (TypeError, ValueError):
            continue
        if lap_n in seen:
            continue
        t = _td_seconds(row.get("LapStartTime"))
        if t is None:
            continue
        seen.add(lap_n)
        markers.append({"lap": lap_n, "t_s": round(t - t0, 1)})
    return markers


def _load_circuit_info(session) -> Any:
    """Load circuit corners/rotation without requiring a perfect reference lap.

    FastF1's Session.get_circuit_info() always calls add_marker_distance(), which
    can fail (e.g. Monaco 2026 red-flag sessions). We fetch the raw CircuitInfo
    instead and optionally attach distances when possible.
    """
    try:
        from fastf1.mvapi import get_circuit_info as mv_get_circuit_info
    except Exception:
        try:
            return session.get_circuit_info()
        except Exception as exc:
            logger.warning("circuit info unavailable: %s", exc)
            return None

    try:
        circuit_key = session.session_info["Meeting"]["Circuit"]["Key"]
        short = session.session_info["Meeting"]["Circuit"].get("ShortName", "")
        if circuit_key == 149 and short == "Mugello":
            circuit_key = 146
        year = session.event.year
        info = mv_get_circuit_info(year=year, circuit_key=circuit_key)
    except Exception as exc:
        logger.warning("mvapi circuit info failed: %s", exc)
        try:
            return session.get_circuit_info()
        except Exception:
            return None

    try:
        fastest = session.laps.pick_fastest()
        if fastest is not None:
            info.add_marker_distance(reference_lap=fastest)
    except Exception as exc:
        logger.debug("Skipping corner distance annotation: %s", exc)
    return info


def build_replay(
    season: int,
    round_num: int,
    session_type: str = "R",
) -> dict[str, Any] | None:
    """Load one race or sprint session and return the compact replay payload."""
    import fastf1

    sess = _session_code(session_type)
    _enable_cache()
    try:
        session = fastf1.get_session(season, round_num, sess)
        session.load(laps=True, telemetry=True, weather=False, messages=True)
    except Exception as exc:
        logger.error("Failed to load %d %s%d: %s", season, sess, round_num, exc)
        return None

    event = getattr(session, "event", None)
    event_name = display_event_name(
        season,
        round_num,
        getattr(event, "EventName", "") if event is not None else "",
    )
    if sess == "S" and event_name and "sprint" not in event_name.lower():
        event_name = f"{event_name} Sprint"
    circuit = getattr(event, "Location", "") if event is not None else ""

    laps = getattr(session, "laps", None)
    if laps is None or (hasattr(laps, "empty") and laps.empty):
        logger.error("No laps for %d %s%d", season, sess, round_num)
        return None

    t0 = _race_t0_seconds(laps)
    # Race end: last finished lap start + lap time, or max position SessionTime
    end_candidates: list[float] = []
    for _, row in laps.iterrows():
        t = _td_seconds(row.get("LapStartTime"))
        lt = _td_seconds(row.get("LapTime"))
        if t is not None and lt is not None:
            end_candidates.append(t + lt - t0)
        elif t is not None:
            end_candidates.append(t - t0)
    duration_s = int(max(end_candidates)) if end_candidates else 0
    if duration_s < 60:
        logger.error("Duration too short for %d %s%d (%ds)", season, sess, round_num, duration_s)
        return None
    # Cap pathological outliers (e.g. red-flag session clocks)
    duration_s = min(duration_s, 60 * 60 * 4)

    circuit_info = _load_circuit_info(session)
    rotation = float(getattr(circuit_info, "rotation", 0) or 0) if circuit_info is not None else 0.0

    center = _build_centerline(session, laps)
    if center is None:
        logger.info("Falling back to single-lap centerline for %d %s%d", season, sess, round_num)
        center = _pick_centerline_lap(session, laps)
    if center is None:
        logger.error("No centerline for %d %s%d", season, sess, round_num)
        return None
    cx, cy = _rotate_xy(center[0], center[1], rotation)

    smooth_x, smooth_y = _resample_closed_curve(cx, cy, CENTERLINE_POINTS)

    pit_spans = _pit_windows(laps)
    pitlane_world = _build_pitlane(
        _raw_pos_traces(session), pit_spans, rotation, smooth_x, smooth_y
    )

    # Pad around the track itself. Car samples are not used for bounds because a
    # single GPS spike would inflate the whole box.
    pad_frac = 0.06
    bx = smooth_x if pitlane_world is None else np.concatenate([smooth_x, pitlane_world[0]])
    by = smooth_y if pitlane_world is None else np.concatenate([smooth_y, pitlane_world[1]])
    min_x, max_x = float(np.nanmin(bx)), float(np.nanmax(bx))
    min_y, max_y = float(np.nanmin(by)), float(np.nanmax(by))
    span = max(max_x - min_x, max_y - min_y)
    pad = span * pad_frac
    bounds = (min_x - pad, max_x + pad, min_y - pad, max_y + pad)

    proj = Projection(bounds)
    qx, qy = proj.apply(smooth_x, smooth_y)
    centerline = _polyline(qx, qy, CENTERLINE_POINTS)
    outline = _polyline(qx, qy, OUTLINE_POINTS)

    pitlane: list[list[int]] = []
    if pitlane_world is not None:
        plx, ply = proj.apply(pitlane_world[0], pitlane_world[1])
        # Open path — unlike the racing line it must not be closed back up
        step = max(1, len(plx) // OUTLINE_POINTS)
        pitlane = [[int(plx[i]), int(ply[i])] for i in range(0, len(plx), step)]

    corners: list[dict[str, Any]] = []
    if circuit_info is not None and getattr(circuit_info, "corners", None) is not None:
        cdf = circuit_info.corners
        if cdf is not None and len(cdf) > 0 and "X" in cdf.columns:
            corn_x, corn_y = _rotate_xy(
                cdf["X"].to_numpy(dtype=float),
                cdf["Y"].to_numpy(dtype=float),
                rotation,
            )
            cqx, cqy = proj.apply(corn_x, corn_y)
            for i in range(len(cdf)):
                number = cdf.iloc[i].get("Number", i + 1)
                letter = str(cdf.iloc[i].get("Letter") or "").strip()
                try:
                    n = int(number)
                except (TypeError, ValueError):
                    n = i + 1
                label = f"{n}{letter}" if letter else str(n)
                corners.append({"n": n, "label": label, "x": int(cqx[i]), "y": int(cqy[i])})

    drivers = _driver_meta(session, laps, t0, duration_s)
    if not drivers:
        logger.error("No drivers for %d %s%d", season, sess, round_num)
        return None

    on_track = _make_offtrack_filter(smooth_x, smooth_y)
    pos, world = _build_positions(session, drivers, t0, duration_s, proj, rotation, on_track)
    prog, geom_share = _build_progress(
        laps, drivers, world, smooth_x, smooth_y, t0, duration_s
    )
    shares = [v for v in geom_share.values() if v > 0]
    logger.info(
        "Progress from geometry for %d/%d cars (median %.0f%% of frames)",
        len(shares),
        len(drivers),
        100 * float(np.median(shares)) if shares else 0.0,
    )

    pit_windows_rel = {
        code: [[round(a - t0, 1), round(b - t0, 1)] for a, b in spans]
        for code, spans in pit_spans.items()
    }
    stints, pits = _build_stints_and_pits(laps, t0)
    track_status = getattr(session, "track_status", None)
    session_status = getattr(session, "session_status", None)
    flags = _build_flags(track_status, t0, duration_s, session_status=session_status)
    lap_markers = _build_lap_markers(laps, t0)
    feed = _build_feed(session, t0, duration_s)

    total_laps = int(laps["LapNumber"].max()) if "LapNumber" in laps.columns else 0

    event_date = ""
    for attr in ("Session5Date", "EventDate"):
        value = getattr(event, attr, None) if event is not None else None
        if value is not None and not pd.isna(value):
            try:
                event_date = pd.Timestamp(value).date().isoformat()
                break
            except (TypeError, ValueError):
                continue

    return {
        "season": season,
        "round": round_num,
        "session": sess,
        "event_name": event_name,
        "circuit": circuit,
        "country": getattr(event, "Country", "") if event is not None else "",
        "event_date": event_date,
        "hz": HZ,
        "duration_s": duration_s,
        "total_laps": total_laps,
        "track": {
            "rotation": rotation,
            "q_max": Q_MAX,
            "q_w": proj.q_w,
            "q_h": proj.q_h,
            "centerline": centerline,
            "outline": outline,
            "corners": corners,
            **({"pitlane": pitlane} if pitlane else {}),
        },
        "drivers": drivers,
        # Emitted only when the position feed was unusable for running order, so
        # the site can warn that order steps at lap crossings instead of flowing.
        # Absent otherwise, which keeps unaffected races byte-identical on rebuild.
        **({"order_source": "timing"} if not shares else {}),
        "pos": pos,
        "prog": prog,
        "pit_windows": pit_windows_rel,
        "stints": stints,
        "pits": pits,
        "flags": flags,
        "lap_markers": lap_markers,
        "feed": feed,
    }



def _session_code(session: str) -> str:
    """Normalize FastF1 session identifiers to R (race) or S (sprint)."""
    s = (session or "R").strip().upper()
    if s in {"S", "SPRINT"}:
        return "S"
    return "R"


def _replay_stem(season: int, round_num: int, session: str = "R") -> str:
    """Filename stem: 2026_9 for a race, 2026_9_S for a sprint."""
    code = _session_code(session)
    if code == "S":
        return f"{season}_{round_num}_S"
    return f"{season}_{round_num}"


def _index_key(round_num: int, session: str = "R") -> str:
    return f"{int(round_num)}_{_session_code(session)}"

def write_replay(payload: dict[str, Any], dest_dir: Path | None = None) -> Path:
    out_dir = Path(OUTPUTS_DIR) / "replays" if dest_dir is None else Path(dest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_replay_stem(payload['season'], payload['round'], payload.get('session', 'R'))}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    size_kb = path.stat().st_size / 1024
    logger.info(
        "Wrote %s (%.0f KB, %ds, %d drivers)",
        path.name,
        size_kb,
        payload["duration_s"],
        len(payload["drivers"]),
    )
    return path


def _index_winner(race: dict[str, Any]) -> dict[str, Any] | None:
    """The race winner, for the all-races cards.

    Falls back to whatever a previous index carried, because partial rebuilds
    reduce untouched races to a stub without a `drivers` list.
    """
    for drv in race.get("drivers", []) or []:
        if drv.get("finish_position") == 1:
            return {
                "code": drv.get("code", ""),
                "name": drv.get("name", ""),
                "team": drv.get("team", ""),
                "color": drv.get("color", ""),
            }
    prior = race.get("winner")
    return prior if isinstance(prior, dict) and prior.get("code") else None


def write_index(
    races: list[dict[str, Any]],
    season: int,
    dest_dir: Path | None = None,
) -> Path:
    out_dir = Path(OUTPUTS_DIR) if dest_dir is None else Path(dest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "replays_index.json"
    payload = {
        "season": season,
        "races": [
            {
                "season": r["season"],
                "round": r["round"],
                "session": _session_code(r.get("session", "R")),
                "event_name": r["event_name"],
                "circuit": r.get("circuit", ""),
                "country": r.get("country", ""),
                "event_date": r.get("event_date", ""),
                "duration_s": r.get("duration_s", 0),
                "total_laps": r.get("total_laps", 0),
                "driver_count": len(r.get("drivers", []) or []) or r.get("driver_count", 0),
                **({"winner": w} if (w := _index_winner(r)) else {}),
                # Small outline + box so the card grid renders thumbnails
                # without downloading a ~1 MB replay per race.
                "q_w": (r.get("track") or {}).get("q_w", Q_MAX),
                "q_h": (r.get("track") or {}).get("q_h", Q_MAX),
                "outline": (r.get("track") or {}).get("outline", []),
                "file": f"replays/{_replay_stem(r['season'], r['round'], r.get('session', 'R'))}.json",
            }
            for r in races
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Wrote index → %s (%d races)", path, len(payload["races"]))
    return path


def _jobs_for(
    season: int,
    rounds: list[int],
    sessions: list[str],
) -> list[tuple[int, str]]:
    """(round, session) pairs to build, sprint-before-race within a weekend."""
    sprint_set = set(SPRINT_ROUNDS_2026) if season == CURRENT_SEASON else set()
    # For other seasons FastF1's event schedule is the source of truth; callers
    # pass explicit sprint rounds via --rounds together with --session S.
    jobs: list[tuple[int, str]] = []
    for rnd in rounds:
        for sess in sessions:
            if sess == "S" and season == CURRENT_SEASON and rnd not in sprint_set:
                continue
            jobs.append((rnd, sess))
    # Sprint before race on the same weekend (Saturday → Sunday)
    jobs.sort(key=lambda j: (j[0], 0 if j[1] == "S" else 1))
    return jobs


def build_replays(
    season: int = CURRENT_SEASON,
    rounds: list[int] | None = None,
    *,
    sessions: list[str] | None = None,
    skip_existing: bool = False,
) -> list[Path]:
    """Build replay JSON for the given rounds/sessions.

    Default sessions are race + sprint. Sprint weekends come from
    ``SPRINT_ROUNDS_2026`` for the current season.
    """
    _enable_cache()
    if rounds is None:
        rounds = sorted(RACES_2026.keys())
    if sessions is None:
        sessions = ["R", "S"]
    sessions = [_session_code(s) for s in sessions]

    out_dir = Path(OUTPUTS_DIR) / "replays"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    payloads: list[dict[str, Any]] = []

    # Keep previously built sessions in the index when doing partial rebuilds.
    # Keyed by "{round}_{session}" so a sprint and its Sunday race coexist.
    existing_index = Path(OUTPUTS_DIR) / "replays_index.json"
    prior: dict[str, dict[str, Any]] = {}
    if existing_index.exists():
        try:
            data = json.loads(existing_index.read_text(encoding="utf-8"))
            for r in data.get("races", []):
                if r.get("season") == season:
                    prior[_index_key(int(r["round"]), r.get("session", "R"))] = r
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            prior = {}

    for rnd, sess in _jobs_for(season, rounds, sessions):
        dest = out_dir / f"{_replay_stem(season, rnd, sess)}.json"
        if skip_existing and dest.exists():
            logger.info("Skip existing %s", dest.name)
            try:
                payloads.append(json.loads(dest.read_text(encoding="utf-8")))
                written.append(dest)
            except (json.JSONDecodeError, OSError):
                pass
            continue
        logger.info("Building replay %d %s%d …", season, sess, rnd)
        try:
            payload = build_replay(season, rnd, session_type=sess)
        except Exception:
            # A round with no session data yet must not abort the whole build.
            logger.warning(
                "Skipping %d %s%d (no data available)", season, sess, rnd, exc_info=False
            )
            continue
        if payload is None:
            logger.warning("Skipping %d %s%d (build failed)", season, sess, rnd)
            continue
        written.append(write_replay(payload))
        payloads.append(payload)

    # Merge into full index for the season (built + prior not rebuilt)
    by_key: dict[str, dict[str, Any]] = {}
    for r in prior.values():
        sess = _session_code(r.get("session", "R"))
        fpath = out_dir / f"{_replay_stem(season, int(r['round']), sess)}.json"
        if fpath.exists():
            try:
                by_key[_index_key(int(r["round"]), sess)] = json.loads(
                    fpath.read_text(encoding="utf-8")
                )
                continue
            except (json.JSONDecodeError, OSError):
                pass
        by_key[_index_key(int(r["round"]), sess)] = {
            "season": season,
            "round": int(r["round"]),
            "session": sess,
            "event_name": r.get("event_name", ""),
            "circuit": r.get("circuit", ""),
            "country": r.get("country", ""),
            "event_date": r.get("event_date", ""),
            "duration_s": r.get("duration_s", 0),
            "total_laps": r.get("total_laps", 0),
            "driver_count": r.get("driver_count", 0),
            "winner": r.get("winner"),
            "track": {
                "q_w": r.get("q_w", Q_MAX),
                "q_h": r.get("q_h", Q_MAX),
                "outline": r.get("outline", []),
            },
        }
    for p in payloads:
        by_key[_index_key(int(p["round"]), p.get("session", "R"))] = p

    ordered = sorted(
        by_key.values(),
        key=lambda r: (int(r["round"]), 0 if _session_code(r.get("session", "R")) == "S" else 1),
    )
    write_index(ordered, season)
    return written


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build DeltaV race replay JSON")
    parser.add_argument("--season", type=int, default=CURRENT_SEASON)
    parser.add_argument(
        "--rounds",
        type=str,
        default=None,
        help="Comma-separated rounds, e.g. 1,2,3",
    )
    parser.add_argument("--max-round", type=int, default=None, help="Inclusive max round")
    parser.add_argument(
        "--session",
        type=str,
        default="all",
        help="R (race), S (sprint), or all (default)",
    )
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Copy outputs into site/public/api after build",
    )
    args = parser.parse_args()

    rounds: list[int] | None
    if args.rounds:
        rounds = [int(x.strip()) for x in args.rounds.split(",") if x.strip()]
    elif args.max_round is not None:
        rounds = [r for r in sorted(RACES_2026.keys()) if r <= args.max_round]
    else:
        rounds = None

    sess_arg = (args.session or "all").strip().upper()
    if sess_arg in {"ALL", "BOTH", "*"}:
        sessions = ["R", "S"]
    elif sess_arg in {"S", "SPRINT"}:
        sessions = ["S"]
        # Sprint-only with no rounds → every scheduled sprint weekend
        if rounds is None:
            rounds = list(SPRINT_ROUNDS_2026) if args.season == CURRENT_SEASON else []
    else:
        sessions = ["R"]

    paths = build_replays(
        args.season, rounds, sessions=sessions, skip_existing=args.skip_existing
    )
    if args.sync:
        from sync_site_api import sync_replays

        sync_replays()
    logger.info("Done — %d replay file(s)", len(paths))
    return 0 if paths else 1


if __name__ == "__main__":
    raise SystemExit(main())
