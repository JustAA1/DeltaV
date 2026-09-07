# DeltaV

Formula 1 championship standings, race replays, podium history, and “What If?” alternate standings.


| Folder      | Role                                             |
| ----------- | ------------------------------------------------ |
| `site/`     | React (Vite) UI — host on **Vercel**             |
| `api/`      | FastAPI — **local only** (What If compute)       |
| `pipeline/` | Ingest, leaderboards, replays, podigami, sync |


---

## Site features

- **Leaderboard** — Progressive drivers’ / constructors’ championship chart (1980–2026), plus **Formula 1.5** (midfield-only, 2021–2026) and **Reversed** (classified finishing order flipped; DNFs excluded).
- **Replays** — Track-map playback of completed 2026 races:
  - Play/pause, scrubber, and speed controls (1×–20×)
  - Live running order with gaps, tyre compounds, and pit counts
  - Race-control feed and per-driver overlays (stints, grid→live delta)
- **Podigami** — Unique podium combinations across F1 history (recent, yearly + all-time stats). Heavily inspired by [NFL Scorigami](https://www.youtube.com/watch?v=9l5C8cGMueY) with tracking first-time outcomes.
- **What If?** — Guided scenarios:
  - *Remove from grid* — e.g. “What if Mercedes didn’t race in 2026?”
  - *Swap points system* — e.g. “What if 2021 had the points system from 2007?”
  - Currently, the defaults (Mercedes 2026 / 2021←2007) work on the live site as they are in static JSON, however, custom scenarios need the local API and can only be accessed when running the site locally.

Precomputed JSON lives in `site/public/api/` so the public site stays static.

---



## Run locally

You will need two terminals: the API (to compute alternate standings) and the Vite site (proxies `/api/what-if` and `/api/health` to it).

### 1. API

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

Leave this running. Health check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### 2. Site

```bash
cd site
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) → **What If?** → change year / team / points years → **View alternate standings**.

---



## Pipeline

Refresh static site data from FastF1 (leaderboards, Formula 1.5, replays, podigami, hosted What If defaults):

```bash
cd pipeline
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python precompute.py
```

Useful flags: `--skip-ingest`, `--skip-assets`, `--skip-replays`, `--current-only`, `--max-round N`.