import json, subprocess, tempfile, sys
from pydantic import BaseModel

class ScreenParams(BaseModel):
    lambda_eff: float | None = None
    mu_star: float
    omega_log_meV: float | None = None
    omega2_meV: float | None = None
    alpha2F_csv: str | None = None
    units: str = "meV"

def run_ad_screen(p: ScreenParams) -> dict:
    cmd = [sys.executable, "quantum-rtsc-protocol/tools/eliashberg_runner.py", "--mu_star", str(p.mu_star)]
    if p.alpha2F_csv:
        cmd += ["--alpha2F_csv", p.alpha2F_csv, "--units", p.units]
    else:
        cmd += ["--lambda_eff", str(p.lambda_eff), "--omega_log_meV", str(p.omega_log_meV)]
        if p.omega2_meV: cmd += ["--omega2_meV", str(p.omega2_meV)]
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
        out = f.name
    cmd += ["--json-out", out]
    rc = subprocess.run(cmd, check=False).returncode
    data = json.load(open(out))
    return {"result": data, "exit_code": rc, "escalate": (rc == 10)}
