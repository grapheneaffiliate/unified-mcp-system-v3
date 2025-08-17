from __future__ import annotations
import math
from typing import Any, Mapping, TypedDict

from .base import BaseTool

class TcResult(TypedDict):
    tc: float
    details: dict[str, float]

class SuperconductivityCalculatorTool(BaseTool):
    """
    Calculates the superconducting critical temperature (Tc) using the
    McMillan-Allen-Dynes formula with plasmonic correction.
    """

    name = "superconductivity_calculator"

    def run(
        self,
        *,
        lambda_ep: float,
        lambda_pl: float,
        mu_star: float,
        omega_log: float,
        t_c_cap: float | None = None,
    ) -> TcResult:
        """Allen–Dynes/McMillan style estimate with plasmonic correction."""
        lambda_total = lambda_ep + lambda_pl

        f1 = (1 + (lambda_total / 2.46)) ** (1 / 3)
        f2 = 1 + ((omega_log / 1000.0) - 1) * (lambda_total ** 2) / (lambda_total ** 2 + 3.0)

        exponent_numerator = 1.04 * (1 + lambda_total)
        exponent_denominator = lambda_total - mu_star * (1 + 0.62 * lambda_total)
        exponent = -exponent_numerator / exponent_denominator

        tc = (f1 * f2 * omega_log / 1.2) * math.exp(exponent)

        if t_c_cap is not None:
            tc = min(tc, t_c_cap)

        return TcResult(
            tc=tc,
            details={
                "lambda_total": lambda_total,
                "f1": f1,
                "f2": f2,
                "exponent": exponent,
            },
        )
