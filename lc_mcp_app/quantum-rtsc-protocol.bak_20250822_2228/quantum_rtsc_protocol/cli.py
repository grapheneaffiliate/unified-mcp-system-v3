import argparse
import json
import math
import sys
from datetime import datetime
import subprocess

K_PER_MEV = 11.60451812155008

def calc_tc(omega_log_value, omega_units, lam, mu_star, f_omega):
    """Calculate Tc using Allen-Dynes formula with comprehensive input validation."""
    # convert ω_log to Kelvin
    u = omega_units.lower()
    if u in ("mev", "meV", "mev"):
        omega_log_K = omega_log_value * K_PER_MEV
    elif u in ("k", "kelvin", "k"):
        omega_log_K = omega_log_value
    else:
        raise ValueError("omega-units must be 'meV' or 'K'")
    
    # Enhanced physics validation guards
    if u in ("mev", "meV", "mev"):
        if not (10 <= omega_log_value <= 1000):
            raise ValueError(f"omega_log={omega_log_value} out of physical range [10, 1000] {omega_units}")
    else:  # Kelvin units
        if not (100 <= omega_log_value <= 12000):
            raise ValueError(f"omega_log={omega_log_value} out of physical range [100, 12000] {omega_units}")
    
    if lam <= 0:
        raise ValueError(f"lambda={lam} must be > 0 (electron-phonon coupling strength)")
    if lam > 10:
        raise ValueError(f"lambda={lam} unrealistically large (typical range: 0.1-5.0)")
    
    if not (0.01 < mu_star < 0.3):
        raise ValueError(f"mu*={mu_star} must be in (0.01, 0.3) (Coulomb pseudopotential range)")
    
    if not (1.0 <= f_omega <= 1.5):
        raise ValueError(f"f_omega={f_omega} out of allowed range [1.0, 1.5] (spectral shape factor)")
    
    # Critical Allen-Dynes denominator check
    den = lam - mu_star * (1 + 0.62 * lam)
    if den <= 0:
        critical_mu = lam / (1 + 0.62 * lam)
        raise ValueError(f"Allen-Dynes denominator={den:.4f} ≤ 0. For λ={lam}, need μ* < {critical_mu:.4f}")
    
    # Warn if denominator is very small (unstable regime)
    if den < 0.1:
        import warnings
        warnings.warn(f"Small denominator={den:.4f} may indicate unstable parameter regime", UserWarning)
    
    # Allen-Dynes calculation with overflow protection
    exponent = -1.04 * (1 + lam) / den
    if exponent < -50:  # Prevent underflow
        raise ValueError(f"Exponential term too small (exp({exponent:.2f})) - parameters yield negligible Tc")
    
    base = (omega_log_K / 1.2) * math.exp(exponent)
    
    # Provenance information
    now = datetime.utcnow().isoformat() + "Z"
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        sha = None
    
    return {
        "provenance": {"timestamp_utc": now, "git_sha": sha},
        "inputs": {
            "omega_log": omega_log_value,
            "omega_units": omega_units,
            "lambda": lam,
            "mu_star": mu_star,
            "f_omega": f_omega,
        },
        "derived": {"omega_log_K": omega_log_K, "denominator": den},
        "results": {"Tc_K": base * f_omega},
        "status": "ok",
    }

def main():
    p = argparse.ArgumentParser(prog="rtsc")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("calc", help="Compute Tc from Allen–Dynes inputs")
    c.add_argument("--omega-log", type=float, required=True)
    c.add_argument("--omega-units", type=str, default="meV", help="meV or K")
    c.add_argument("--lambda-val", type=float, required=True, dest="lambda_val")
    c.add_argument("--mu-star", type=float, required=True, dest="mu_star")
    c.add_argument("--f-omega", type=float, required=True, dest="f_omega")

    args = p.parse_args()
    try:
        out = calc_tc(args.omega_log, args.omega_units, args.lambda_val, args.mu_star, args.f_omega)
        print(json.dumps(out, indent=2, sort_keys=True))
    except Exception as e:
        err = {"status": "error", "error": str(e)}
        print(json.dumps(err, indent=2, sort_keys=True), file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
