# mcp_agent/tools/plogic_bo.py
# v2.1: async/sync bridge for skopt via run_coroutine_threadsafe, LRU+TTL cache,
# safer extra args, rich errors, persistence, timeouts, health check, Prometheus metrics,
# thread-count gauge, env-tunable workers, trace ring-buffer cap, optional schema tool.

from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal, Tuple
import os, sys, json, csv, tempfile, subprocess, asyncio, time, math, uuid, hashlib, pickle, re, logging, traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from collections import OrderedDict
from pathlib import Path

# -------- Optional deps (graceful degradation) ----------
try:
    import redis
except Exception:
    redis = None

try:
    import mlflow
except Exception:
    mlflow = None

try:
    from skopt import gp_minimize
    from skopt.space import Real
    _HAS_SKOPT = True
except Exception:
    _HAS_SKOPT = False

try:
    from prometheus_client import Counter, Histogram, Gauge
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False

import threading

_LOG = logging.getLogger("plogic_bo")
_LOG.setLevel(logging.INFO)

# -------- Config ----------
_PLOGIC_SRC = os.getenv("PLOGIC_SRC", "/app/external/photonic-logic/src")
_REDIS_URL = os.getenv("REDIS_URL")
_RESULTS_DIR = Path(os.getenv("PLOGIC_RESULTS", "/data/plogic_results"))
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_MAX_WORKERS = int(os.getenv("PLOGIC_MAX_WORKERS", str(min(4, (os.cpu_count() or 2)))))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS)

CASCADE_TIMEOUT = float(os.getenv("PLOGIC_TIMEOUT", "60"))
CHAR_TIMEOUT = float(os.getenv("PLOGIC_CHAR_TIMEOUT", "30"))
TRUTH_TIMEOUT = float(os.getenv("PLOGIC_TRUTH_TIMEOUT", "45"))
OBJ_TIMEOUT = float(os.getenv("PLOGIC_OBJECTIVE_TIMEOUT", "60"))

# -------- Prometheus (optional) ----------
if _HAS_PROM:
    MET_RUNS = Counter("plogic_cascade_total", "Total cascade runs")
    MET_RUNS_ERR = Counter("plogic_cascade_errors_total", "Total cascade errors")
    MET_DUR = Histogram("plogic_cascade_duration_seconds", "Cascade duration (s)")
    MET_BO_OBJ = Histogram("plogic_bo_objective", "Objective values (ber - alpha*margin)")
    THREADS_G = Gauge("plogic_threads", "Active Python threads")
else:
    class _Null:
        def labels(self, *_, **__): return self
        def observe(self, *_): pass
        def inc(self, *_): pass
        def set(self, *_): pass
    MET_RUNS = MET_RUNS_ERR = MET_DUR = MET_BO_OBJ = THREADS_G = _Null()

def _observe_threads():
    try:
        THREADS_G.set(len(threading.enumerate()))
    except Exception:
        pass

# -------- Capability log ----------
def _redis():
    if not _REDIS_URL or not redis:
        return None
    try:
        return redis.Redis.from_url(_REDIS_URL, decode_responses=True)
    except Exception:
        return None

def _log_capabilities():
    caps = []
    caps.append(f"Cache: {'Redis' if _redis() else 'In-memory LRU+TTL'}")
    caps.append(f"BO: {'GP-based' if _HAS_SKOPT else 'Random search'}")
    caps.append(f"Tracking: {'MLflow' if mlflow else 'Disabled'}")
    caps.append(f"Metrics: {'Prometheus' if _HAS_PROM else 'Disabled'}")
    _LOG.info("plogic_bo capabilities: %s", ", ".join(caps))

_log_capabilities()

# -------- LRU + TTL cache (fallback) ----------
class _LRUTTL:
    def __init__(self, max_items=1024):
        self._store: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._max = max_items
    def get(self, key: str):
        now = time.time()
        item = self._store.get(key)
        if not item: return None
        exp, data = item
        if exp < now:
            self._store.pop(key, None); return None
        self._store.move_to_end(key)
        return data
    def setex(self, key: str, ttl: int, value: Any):
        now = time.time()
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (now + ttl, value)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

_LRU = _LRUTTL()

# -------- Utils ----------
def _json_dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

def _digest(obj: Any) -> str:
    if isinstance(obj, dict):
        key_str = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        return hashlib.blake2b(key_str.encode(), digest_size=16).hexdigest()
    try:
        return hashlib.md5(pickle.dumps(obj, protocol=4)).hexdigest()
    except Exception:
        return hashlib.blake2b(_json_dumps(obj).encode(), digest_size=16).hexdigest()

def _env_with_plogic() -> Dict[str, str]:
    env = os.environ.copy()
    if _PLOGIC_SRC and os.path.isdir(_PLOGIC_SRC):
        pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (pp + (":" if pp else "") + _PLOGIC_SRC)
    return env

def _run_cli(args: List[str]) -> Tuple[int, str, str]:
    env = _env_with_plogic()
    cmd = [sys.executable, "-m", "plogic.cli", *args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    return proc.returncode, proc.stdout, proc.stderr

def _parse_json_or_raw(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s}

def _maybe_mlflow_log(params: Dict[str, Any], metrics: Dict[str, float], artifacts: List[str]):
    if not mlflow:
        return
    try:
        with mlflow.start_run():
            loggable = {k: v for k, v in params.items() if isinstance(v, (int, float, str, bool))}
            if loggable: mlflow.log_params(loggable)
            for k, v in metrics.items():
                if isinstance(v, (int, float)) and math.isfinite(float(v)):
                    mlflow.log_metric(k, float(v))
            for p in artifacts:
                if isinstance(p, str) and os.path.exists(p):
                    try: mlflow.log_artifact(p)
                    except Exception: pass
    except Exception as e:
        _LOG.debug("MLflow logging skipped: %s", e)

# -------- Safer EXTRA args ----------
ALLOWED_EXTRA_PATTERN = re.compile(r"^--[a-z][a-z0-9-]*(?:=[\w.\-+eE]+)?$", re.I)
def _validate_extra(extra: List[str]) -> List[str]:
    ok = []
    for arg in extra:
        s = str(arg)
        if ALLOWED_EXTRA_PATTERN.match(s):
            ok.append(s)
        else:
            _LOG.warning("Skipping suspicious extra arg: %s", s)
    return ok

# -------- Cache decorator ----------
def physics_cache(expire_seconds: int = 3600):
    def deco(fn):
        async def wrapper(*args, **kwargs):
            interesting = {k: kwargs.get(k) for k in [
                "threshold","beta","xpm_mode","n2","a_eff","n_eff","g_geom","ctrl","extra"
            ]}
            interesting["__op__"] = fn.__name__
            key = _digest(interesting)
            r = _redis()
            if r:
                hit = r.get(f"plogic:{key}")
                if hit: return json.loads(hit)
            else:
                hit = _LRU.get(f"plogic:{key}")
                if hit: return hit
            out = await fn(*args, **kwargs)
            payload = _json_dumps(out)
            if r:
                r.setex(f"plogic:{key}", expire_seconds, payload)
            else:
                _LRU.setex(f"plogic:{key}", expire_seconds, out)
            return out
        return wrapper
    return deco

# -------- Core wrappers with timeouts ----------
async def plogic_characterize() -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    async def _impl():
        rc, so, se = await loop.run_in_executor(_EXECUTOR, _run_cli, ["characterize"])
        if rc != 0: raise RuntimeError(se.strip() or "plogic characterize failed")
        return _parse_json_or_raw(so)
    out = await asyncio.wait_for(_impl(), timeout=CHAR_TIMEOUT)
    if isinstance(out, dict):
        out.setdefault("run_id", str(uuid.uuid4()))
        out.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
    return out

async def plogic_truth_table(ctrl: List[float], out_csv: Optional[str] = None) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    async def _impl():
        path = out_csv
        if not path:
            fd, path = tempfile.mkstemp(suffix=".csv"); os.close(fd)
        args = ["truth-table"]
        for c in ctrl: args += ["--ctrl", str(c)]
        args += ["--out", path]
        rc, so, se = await loop.run_in_executor(_EXECUTOR, _run_cli, args)
        if rc != 0: raise RuntimeError(se.strip() or "plogic truth-table failed")
        rows: List[Dict[str, Any]] = []
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows.append(r)
        return path, rows
    path, rows = await asyncio.wait_for(_impl(), timeout=TRUTH_TIMEOUT)
    return {"run_id": str(uuid.uuid4()), "timestamp": datetime.utcnow().isoformat() + "Z", "path": path, "rows": rows}

@physics_cache(expire_seconds=1800)
async def plogic_cascade(
    threshold: Literal["hard","soft"]="soft",
    beta: float = 30.0,
    xpm_mode: Literal["linear","physics"]="physics",
    n2: Optional[float] = 1e-17,
    a_eff: Optional[float] = None,
    n_eff: Optional[float] = None,
    g_geom: Optional[float] = None,
    extra: Optional[List[str]] = None
) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    async def _impl():
        args = ["cascade", "--threshold", threshold, "--beta", str(beta), "--xpm-mode", xpm_mode]
        if n2 is not None: args += ["--n2", str(n2)]
        if a_eff is not None: args += ["--a-eff", str(a_eff)]
        if n_eff is not None: args += ["--n-eff", str(n_eff)]
        if g_geom is not None: args += ["--g-geom", str(g_geom)]
        if extra: args += _validate_extra(list(map(str, extra)))
        t0 = time.time()
        rc, so, se = await loop.run_in_executor(_EXECUTOR, _run_cli, args)
        dt = time.time() - t0
        MET_DUR.observe(dt); MET_RUNS.inc(); _observe_threads()
        if rc != 0:
            MET_RUNS_ERR.inc()
            raise RuntimeError(se.strip() or "plogic cascade failed")
        out = _parse_json_or_raw(so)
        metrics: Dict[str, float] = {}
        if isinstance(out, dict):
            for k in ["logic_margin","ber_estimate","power_mw","contrast_db"]:
                v = out.get(k)
                if isinstance(v, (int,float)): metrics[k] = float(v)
        else:
            m_margin = re.search(r"margin[:=]\s*([0-9.]+)", so, re.I)
            m_ber = re.search(r"ber[_\s-]?(estimate)?[:=]\s*([0-9.eE+-]+)", so, re.I)
            if m_margin: metrics["logic_margin"] = float(m_margin.group(1))
            if m_ber: metrics["ber_estimate"] = float(m_ber.group(2))
            out = {"raw": so}
        result = {
            "run_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "params": {
                "threshold": threshold, "beta": beta, "xpm_mode": xpm_mode,
                "n2": n2, "a_eff": a_eff, "n_eff": n_eff, "g_geom": g_geom,
                "extra": _validate_extra(extra or [])
            },
            "result": out,
            "metrics": metrics,
            "duration_s": dt,
        }
        _maybe_mlflow_log(result["params"], metrics, artifacts=[])
        return result
    try:
        return await asyncio.wait_for(_impl(), timeout=CASCADE_TIMEOUT)
    except asyncio.TimeoutError:
        MET_RUNS_ERR.inc()
        raise RuntimeError("Cascade simulation timed out")

# -------- Parallel sweep with rich errors ----------
async def plogic_sweep_parallel(configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    tasks = [plogic_cascade(**cfg) for cfg in configs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok, err = [], []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            err.append({
                "error": str(r),
                "type": type(r).__name__,
                "traceback": traceback.format_exc(),
                "config": configs[i] if i < len(configs) else None
            })
        else:
            ok.append(r)
    payload = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "count_ok": len(ok),
        "count_error": len(err),
        "results": ok,
        "errors": err
    }
    with open(_RESULTS_DIR / f"sweep_{payload['run_id']}.json", "w") as f:
        json.dump(payload, f, indent=2)
    return payload

# -------- BO helpers ----------
def _default_space() -> List[Tuple[str, float, float]]:
    return [
        ("n2", 1e-18, 1e-16),
        ("a_eff", 0.1e-12, 2e-12),
        ("n_eff", 1.4, 3.5),
        ("g_geom", 0.5, 1.0),
        ("beta", 10.0, 100.0),
    ]

async def _objective_eval(params: Dict[str, float], fixed: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    kwargs = {**fixed, **params}
    res = await plogic_cascade(**kwargs)
    metrics = res.get("metrics", {}) if isinstance(res, dict) else {}
    ber = float(metrics.get("ber_estimate", 1.0))
    margin = float(metrics.get("logic_margin", 0.0))
    alpha = float(fixed.get("objective_margin_weight", 0.1))
    obj = ber - alpha * margin
    MET_BO_OBJ.observe(obj); _observe_threads()
    _maybe_mlflow_log({**kwargs, "objective": "ber - alpha*margin"}, {"objective": obj, **metrics}, artifacts=[])
    return obj, res

def _make_sync_objective(loop: asyncio.AbstractEventLoop, dims, fixed, trace, best_ref):
    def _sync_obj(pt: List[float]) -> float:
        params = {d.name: v for d, v in zip(dims, pt)}
        fut = asyncio.run_coroutine_threadsafe(_objective_eval(params, fixed), loop)
        try:
            objective, result = fut.result(timeout=OBJ_TIMEOUT)
        except Exception as e:
            _LOG.error("Objective evaluation failed: %s", e)
            objective, result = float("inf"), {"error": str(e), "params": params}
        record = {"params": params, "objective": objective, "metrics": result.get("metrics", {}), "result": result}
        trace.append(record)
        if len(trace) > 500: del trace[:-400]  # ring buffer cap
        if objective < best_ref["objective"]:
            best_ref.update({"objective": objective, "params": params, "result": result})
        _observe_threads()
        return float(objective)
    return _sync_obj

async def plogic_bo_run(
    n_calls: int = 40,
    threshold: Literal["hard","soft"]="soft",
    xpm_mode: Literal["linear","physics"]="physics",
    space_bounds: Optional[Dict[str, List[float]]] = None,
    fixed_params: Optional[Dict[str, Any]] = None,
    objective_margin_weight: float = 0.1,
    random_starts: int = 8,
) -> Dict[str, Any]:
    fixed = dict(fixed_params or {})
    fixed.setdefault("threshold", threshold)
    fixed.setdefault("xpm_mode", xpm_mode)
    fixed.setdefault("objective_margin_weight", float(objective_margin_weight))
    space_def = _default_space()
    if space_bounds:
        space_def = [(name, float(space_bounds.get(name, [lo, hi])[0]),
                             float(space_bounds.get(name, [lo, hi])[1]))
                     for name, lo, hi in space_def]
    trace: List[Dict[str, Any]] = []
    best = {"objective": float("inf"), "params": None, "result": None}
    if _HAS_SKOPT:
        dims = [Real(lo, hi, name=name) for name, lo, hi in space_def]
        loop = asyncio.get_event_loop()
        sync_obj = _make_sync_objective(loop, dims, fixed, trace, best)
        def _skopt_runner():
            return gp_minimize(
                func=sync_obj,
                dimensions=dims,
                n_calls=int(n_calls),
                n_initial_points=int(random_starts),
                acq_func="EI",
                xi=0.01,
            )
        await loop.run_in_executor(_EXECUTOR, _skopt_runner)
    else:
        import random
        async def sample_once() -> None:
            params = {}
            for n, lo, hi in space_def:
                if lo > 0 and hi / lo > 50:
                    u = random.random()
                    val = math.exp(math.log(lo) + u * (math.log(hi) - math.log(lo)))
                else:
                    val = lo + random.random() * (hi - lo)
                params[n] = float(val)
            try:
                obj, res = await asyncio.wait_for(_objective_eval(params, fixed), timeout=OBJ_TIMEOUT)
            except Exception as e:
                obj, res = float("inf"), {"error": str(e), "params": params, "traceback": traceback.format_exc()}
            record = {"params": params, "objective": obj, "metrics": res.get("metrics", {}), "result": res}
            trace.append(record)
            if len(trace) > 500: del trace[:-400]
            if obj < best["objective"]:
                best.update({"objective": obj, "params": params, "result": res})
        remain = int(n_calls)
        batch = min(8, int(max(1, os.cpu_count() or 1)))
        while remain > 0:
            k = min(batch, remain)
            await asyncio.gather(*[sample_once() for _ in range(k)])
            remain -= k
    payload = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "space": [{"name": n, "low": lo, "high": hi} for n, lo, hi in space_def],
        "fixed_params": fixed,
        "best": best,
        "trace_count": len(trace),
        "trace": trace[-200:],
    }
    with open(_RESULTS_DIR / f"bo_run_{payload['run_id']}.json", "w") as f:
        json.dump({"payload": payload, "trace_full": trace}, f, indent=2)
    return payload

# -------- Health + schema ----------
async def plogic_health() -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    async def _impl():
        rc, _, se = await loop.run_in_executor(_EXECUTOR, _run_cli, ["--help"])
        return {"ok": rc == 0, "stderr": se[:300]}
    try:
        res = await asyncio.wait_for(_impl(), timeout=5)
        return {"status": "healthy" if res["ok"] else "unhealthy", **res}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

async def plogic_schema() -> dict:
    return {
        "tools": ["plogic_truth_table","plogic_cascade","plogic_sweep_parallel","plogic_bo_run","plogic_health","plogic_schema"],
        "has_gp_bo": bool(_HAS_SKOPT),
        "uses_redis": bool(_redis()),
        "max_workers": _MAX_WORKERS
    }

# -------- Tool specs / registry ----------
TOOL_SPECS: List[Dict[str, Any]] = [
    {"type":"function","function":{"name":"plogic_truth_table","description":"Generate photonic-logic truth table for given control powers.","parameters":{"type":"object","properties":{"ctrl":{"type":"array","items":{"type":"number"}},"out_csv":{"type":"string"}},"required":["ctrl"]}}},
    {"type":"function","function":{"name":"plogic_cascade","description":"Run a cascade simulation (physics-mode supported) and return metrics.","parameters":{"type":"object","properties":{"threshold":{"type":"string","enum":["hard","soft"],"default":"soft"},"beta":{"type":"number","default":30.0},"xpm_mode":{"type":"string","enum":["linear","physics"],"default":"physics"},"n2":{"type":"number","nullable":True},"a_eff":{"type":"number","nullable":True},"n_eff":{"type":"number","nullable":True},"g_geom":{"type":"number","nullable":True},"extra":{"type":"array","items":{"type":"string"}}},"required":[]}}},
    {"type":"function","function":{"name":"plogic_sweep_parallel","description":"Run multiple cascade configs in parallel; returns individual results and errors.","parameters":{"type":"object","properties":{"configs":{"type":"array","items":{"type":"object","properties":{"threshold":{"type":"string","enum":["hard","soft"]},"beta":{"type":"number"},"xpm_mode":{"type":"string","enum":["linear","physics"]},"n2":{"type":"number","nullable":True},"a_eff":{"type":"number","nullable":True},"n_eff":{"type":"number","nullable":True},"g_geom":{"type":"number","nullable":True},"extra":{"type":"array","items":{"type":"string"}}},"required":[]}}},"required":["configs"]}}},
    {"type":"function","function":{"name":"plogic_bo_run","description":"Bayesian Optimization over physics parameters (GP if available; else random). Minimizes objective = BER - alpha*margin.","parameters":{"type":"object","properties":{"n_calls":{"type":"integer","default":40},"threshold":{"type":"string","enum":["hard","soft"],"default":"soft"},"xpm_mode":{"type":"string","enum":["linear","physics"],"default":"physics"},"space_bounds":{"type":"object","additionalProperties":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":2}},"fixed_params":{"type":"object"},"objective_margin_weight":{"type":"number","default":0.1},"random_starts":{"type":"integer","default":8}},"required":[]}}},
    {"type":"function","function":{"name":"plogic_health","description":"Quick health check to verify photonic-logic CLI accessibility.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"plogic_schema","description":"List available plogic tools & capabilities.","parameters":{"type":"object","properties":{},"required":[]}}}
]

TOOL_CALLABLES: Dict[str, Any] = {
    "plogic_truth_table": plogic_truth_table,
    "plogic_cascade": plogic_cascade,
    "plogic_sweep_parallel": plogic_sweep_parallel,
    "plogic_bo_run": plogic_bo_run,
    "plogic_health": plogic_health,
    "plogic_schema": plogic_schema,
}

def register_toolset(registry: Any) -> None:
    for spec in TOOL_SPECS:
        fn_name = spec["function"]["name"]
        registry.add(spec, TOOL_CALLABLES[fn_name])
