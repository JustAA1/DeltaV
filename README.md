# DeltaV

Formula 1 race predictions, championship standings, podium history, and “What If?” alternate standings.


| Folder      | Role                                               |
| ----------- | -------------------------------------------------- |
| `site/`     | React (Vite) UI — host on **Vercel**               |
| `api/`      | FastAPI — **local only** (What If compute)         |
| `pipeline/` | Ingest, features, XGBoost model, weekly precompute |


---

## How predictions work

DeltaV ranks the full grid for each race with an **XGBoost learning-to-rank** model (`rank:pairwise`).

1. **Ingest** — The data is gathered with FastF1, as it pulls practice, quali, race, and sprint sessions into parquet.
2. **Features** — One row per driver per race, built only from information available *before* that race (no leakage). Signals include:
  - recent finish / quali form (3- and 5-race windows)
  - constructor quali gap and race pace
  - track history (avg finish / quali at that circuit)
  - grid penalties, DNF rate, tire-stint habits, practice pace gap
3. **Train** — Walk-forward over the season: for each round, train on all earlier races, then predict that race. Older seasons are down-weighted heavily so the current car regulation era dominates.
4. **Predict** — The booster scores every driver in the race group; scores are turned into a predicted finishing order.

Precomputed prediction JSON lives in `site/public/api/` so the public site stays static.

---

## Site features

- **Predictions** — Full-grid order for each 2026 round so far, with predicted-vs-actual when the race is done and a forecast for the next event.
- **Podiumigami** — Unique podium combinations across F1 history (recent, yearly + all-time stats). Heavily inspired by [NFL Scorigami](https://www.youtube.com/watch?v=9l5C8cGMueY) with tracking first-time outcomes.
- **Leaderboard** — Progressive drivers’ / constructors’ championship chart (1980–2026).
- **What If?** — Guided scenarios:
  - *Remove from grid* — e.g. “What if Mercedes didn’t race in 2026?”
  - *Swap points system* — e.g. “What if 2021 had the points system from 2007?”
  - Currently, the defaults (Mercedes 2026 / 2021←2007) work on the live site as they are in static JSON, however, custom scenarios need the local API and can only be accessed when running the site locally.

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

## Future plans

- Improve the predictive model (better features, tuning, and evaluation).
- Add more unconventional statistics beyond the current tabs.
