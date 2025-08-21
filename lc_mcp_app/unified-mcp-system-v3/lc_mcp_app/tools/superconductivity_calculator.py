"""
Tool for calculating the superconducting critical temperature (Tc).
"""

import math
from typing import Any
from .base import BaseTool

class SuperconductivityCalculatorTool(BaseTool):
    """
    Calculates the superconducting critical temperature (Tc) using the
    McMillan-Allen-Dynes formula.
    """

    def __init__(self):
        schema = {
            "type": "object",
            "properties": {
                "lambda_total": {
                    "type": "number",
                    "description": "The total electron-boson coupling strength (λ)."
                },
                "omega_log": {
                    "type": "number",
                    "description": "The logarithmic average boson frequency in Kelvin (ω_log)."
                },
                "mu_star": {
                    "type": "number",
                    "description": "The Coulomb pseudopotential (μ*)."
                },
                "omega_sq_avg_ratio": {
                    "type": "number",
                    "description": "The ratio sqrt(<ω²>)/ω_log for the Allen-Dynes correction factor f2."
                }
            },
            "required": ["lambda_total", "omega_log", "mu_star", "omega_sq_avg_ratio"]
        }
        super().__init__(
            name="calculate_superconducting_tc",
            description="Calculates the superconducting critical temperature (Tc) using the McMillan-Allen-Dynes formula.",
            schema=schema
        )

    async def run(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        lambda_total = kwargs["lambda_total"]
        omega_log = kwargs["omega_log"]
        mu_star = kwargs["mu_star"]
        omega_sq_avg_ratio = kwargs["omega_sq_avg_ratio"]

        # Calculate f1
        f1_base = lambda_total / (2.46 * (1 + 3.8 * mu_star))
        f1 = (1 + f1_base**(3/2))**(1/3)

        # Calculate f2
        f2_numerator = (omega_sq_avg_ratio - 1) * lambda_total**2
        f2_denominator = lambda_total**2 + (1.82 * (1 + 6.3 * mu_star) * omega_sq_avg_ratio)**2
        f2 = 1 + (f2_numerator / f2_denominator)

        # Calculate Tc
        exponent_numerator = 1.04 * (1 + lambda_total)
        exponent_denominator = lambda_total - mu_star * (1 + 0.62 * lambda_total)
        exponent = -exponent_numerator / exponent_denominator
        
        tc = (f1 * f2 * omega_log / 1.2) * math.exp(exponent)

        return {
            "calculated_tc": tc,
            "f1_correction_factor": f1,
            "f2_correction_factor": f2
        }
