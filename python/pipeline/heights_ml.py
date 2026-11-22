"""Predict missing building heights with scikit-learn (F3, course machine-learning option).

Training set: buildings whose height is known from OSM tags or measured from LiDAR.
Features: footprint area, perimeter, compactness, vertex count, building type, and the
mean and maximum known height of other buildings within 60 m. Model: random forest,
checked with 5-fold cross-validation (mean absolute error, meters).
"""
import numpy as np
from scipy.spatial import cKDTree
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score

from .buildings import features
from .common import log

FALLBACK_M = 12.0
TYPES = ["yes", "house", "residential", "apartments", "commercial", "retail", "office", "industrial",
         "church", "school", "university", "hotel", "garage", "parking", "public", "civic", "part"]


def fill(buildings, local):
    """Set b['height'] and b['source'] for every building; return a summary dict."""
    rows = [features(b, local) for b in buildings]
    xy = np.array([[r["x"], r["y"]] for r in rows]) if rows else np.zeros((0, 2))
    known = np.array([b["height"] is not None for b in buildings])
    heights = np.array([b["height"] if b["height"] is not None else np.nan for b in buildings], dtype=float)
    tree = cKDTree(xy[known]) if known.any() else None
    known_h = heights[known]

    known_pos = np.full(len(buildings), -1)
    known_pos[known] = np.arange(known.sum())

    def neighbors(i):
        """Mean and max known height within 60 m, leaving out the building itself."""
        if tree is None:
            return np.nan, np.nan
        values = [known_h[j] for j in tree.query_ball_point(xy[i], 60) if j != known_pos[i]]
        return (float(np.mean(values)), float(np.max(values))) if values else (np.nan, np.nan)

    table = []
    for i, (b, r) in enumerate(zip(buildings, rows)):
        mean_h, max_h = neighbors(i)
        kind = b.get("kind") or "yes"
        table.append([np.log1p(r["area"]), np.log1p(r["perimeter"]), r["compactness"], r["vertices"],
                      TYPES.index(kind) if kind in TYPES else len(TYPES), mean_h, max_h])
    X = np.array(table, dtype=float)
    # Neighborhoods with no known heights: use the overall median.
    for col in (5, 6):
        median = np.nanmedian(X[known, col]) if known.any() and np.isfinite(X[known, col]).any() else FALLBACK_M
        X[np.isnan(X[:, col]), col] = median
    summary = {"known": int(known.sum()), "predicted": int((~known).sum())}
    if known.sum() >= 50 and (~known).any():
        model = RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=0, n_jobs=-1)
        y = np.clip(heights[known], 3, 300)
        mae = -cross_val_score(model, X[known], y, cv=5, scoring="neg_mean_absolute_error").mean()
        model.fit(X[known], y)
        predicted = model.predict(X[~known])
        for i, h in zip(np.flatnonzero(~known), predicted):
            buildings[i]["height"], buildings[i]["source"] = float(h), "model"
        summary.update(model="RandomForestRegressor(200 trees)", cv_mae_m=round(float(mae), 2),
                       features=["log area", "log perimeter", "compactness", "vertices", "building type",
                                 "mean known height within 60 m", "max known height within 60 m"])
        log(f"  height model: trained on {known.sum():,}, predicted {(~known).sum():,}, CV MAE {mae:.1f} m")
    else:
        for b in buildings:
            if b["height"] is None:
                b["height"], b["source"] = FALLBACK_M, "assumed"
        summary.update(model=None, note=f"fewer than 50 known heights; missing heights set to {FALLBACK_M} m")
    return summary
