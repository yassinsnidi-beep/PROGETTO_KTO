"""Company metric computation and normalization."""

from __future__ import annotations

from typing import Any

import numpy as np

from src.utils import safe_float, safe_int


def compute_raw_company_metrics(row: dict[str, Any]) -> dict[str, float]:
    """Compute raw R&D and size metrics for one company."""
    revenues = safe_float(row.get("revenues_th_eur"), 0.0) or 0.0
    employees = safe_int(row.get("employees"), 0) or 0
    rnd_values = [
        safe_float(row.get("rnd_last_year_th_eur"), 0.0) or 0.0,
        safe_float(row.get("rnd_year_minus_1_th_eur"), 0.0) or 0.0,
        safe_float(row.get("rnd_year_minus_2_th_eur"), 0.0) or 0.0,
        safe_float(row.get("rnd_year_minus_3_th_eur"), 0.0) or 0.0,
    ]
    rnd_last_year, _, _, rnd_year_minus_3 = rnd_values
    return {
        "rnd_intensity": rnd_last_year / revenues if revenues > 0 else 0.0,
        "avg_rnd_4y_th_eur": float(np.mean(rnd_values)),
        "rnd_continuity_score": sum(value > 0 for value in rnd_values) / 4.0,
        "rnd_growth_3y": (rnd_last_year - rnd_year_minus_3) / rnd_year_minus_3
        if rnd_year_minus_3 > 0
        else 0.0,
        "company_size_raw": float(np.log1p(max(employees, 0))),
        "revenue_raw": float(np.log1p(max(revenues, 0.0))),
    }


def _robust_minmax(values: list[float], clip: bool = True) -> list[float]:
    if not values:
        return []
    array = np.array(values, dtype=float)
    array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
    if clip and len(array) > 1:
        low, high = np.percentile(array, [1, 99])
        array = np.clip(array, low, high)
    min_value = float(np.min(array))
    max_value = float(np.max(array))
    if max_value == min_value:
        return [0.0 for _ in array]
    return ((array - min_value) / (max_value - min_value)).astype(float).tolist()


def normalize_company_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize selected raw metrics over the whole company dataset."""
    mapping = {
        "rnd_intensity": "rnd_intensity_norm",
        "avg_rnd_4y_th_eur": "avg_rnd_4y_norm",
        "rnd_growth_3y": "rnd_growth_3y_norm",
        "company_size_raw": "company_size_norm",
        "revenue_raw": "revenue_norm",
    }
    for raw_key, norm_key in mapping.items():
        normalized = _robust_minmax([float(row["metrics"].get(raw_key, 0.0)) for row in rows])
        for row, value in zip(rows, normalized):
            row["metrics"][norm_key] = value
    for row in rows:
        metrics = row["metrics"]
        metrics["technology_adoption_capacity_score"] = (
            0.35 * metrics.get("rnd_intensity_norm", 0.0)
            + 0.25 * metrics.get("avg_rnd_4y_norm", 0.0)
            + 0.15 * metrics.get("rnd_continuity_score", 0.0)
            + 0.10 * metrics.get("rnd_growth_3y_norm", 0.0)
            + 0.10 * metrics.get("company_size_norm", 0.0)
            + 0.05 * metrics.get("revenue_norm", 0.0)
        )
    return rows
