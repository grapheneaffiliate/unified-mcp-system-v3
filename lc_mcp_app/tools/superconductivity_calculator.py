from __future__ import annotations

import math
from typing import TypedDict


class TcResult(TypedDict):
    tc_k: float
    method: str


class SuperconductivityCalculatorTool:
    """Estimate Tc using the Allen–Dynes (McMillan) formula.

    Expected params:
      - lambda: electron-phonon coupling constant (λ)
      - mu_star: Coulomb pseudopotential μ* (default 0.13)
      - theta_log: logarithmic-averaged phonon temperature (K)
    """

    name = "superconductivity_calculator"
    description = "Estimate superconducting Tc via Allen–Dynes formula."

    def __call__(self, params: dict[str, float]) -> TcResult:
        lam = float(params["lambda"])
        mu_star = float(params.get("mu_star", 0.13))
        theta_log = float(params["theta_log"])

        denom = 1.04 * (1.0 + lam) - lam * mu_star * (1.0 + 0.62 * lam)
        # Guard against division/pathological values
        if denom <= 0:
            return {"tc_k": 0.0, "method": "allen-dynes"}

        tc = (theta_log / 1.2) * math.exp(-1.04 * (1.0 + lam) / denom)
        return {"tc_k": float(tc), "method": "allen-dynes"}
