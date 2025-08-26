# Photonic-Logic MCP Integration

## What's included
- `mcp_agent/tools/plogic_bo.py` — async tools: health, truth-table, cascade, sweep, BO
- `config/tools.yaml` + `mcp_agent/registry_loader.py` — dynamic tool registration (with strict:false)
- `docker-compose.override.yml` — env + results persistence
- `.github/workflows/plogic-smoke.yml` — CI smoke (JSON + CSV validation)

## Registering tools
If your app constructs a registry object, add:
```python
from mcp_agent.registry_loader import load_and_register_from_file
load_and_register_from_file(registry, "config/tools.yaml")
```

## Env
```
PLOGIC_SRC=/app/external/photonic-logic/src
PLOGIC_RESULTS=/data/plogic_results
PLOGIC_MAX_WORKERS=4
PLOGIC_TIMEOUT=60
PLOGIC_OBJECTIVE_TIMEOUT=60
PLOGIC_CHAR_TIMEOUT=30
PLOGIC_TRUTH_TIMEOUT=45
# REDIS_URL=redis://redis:6379/0
```

## Persistence
Results JSON:
- `sweep_<run_id>.json`
- `bo_run_<run_id>.json`

Mount `/data/plogic_results` to persist across restarts.

### Archival Policy
Results will grow over time. Rotate older than 30 days:
```bash
find /data/plogic_results -type f -mtime +30 -delete
```

## Metrics
Prometheus (optional):
- `plogic_cascade_total`, `plogic_cascade_errors_total`
- `plogic_cascade_duration_seconds`
- `plogic_bo_objective`
- `plogic_threads`

## Resource Guidance

| n_calls | Threads | Est. Runtime (s) | Mem (MB) |
|---------|---------|------------------|----------|
| 4       | 2–4     | < 30             | < 200    |
| 20      | 4–6     | 60–120           | 200–500  |
| 100     | 8+      | 5–10 min         | 1000–2000|

These are rough CI/dev guidelines. Monitor `plogic_threads` and container RSS to tune `PLOGIC_MAX_WORKERS` and timeouts.

## Call surface (OpenAI function-calling)
- `plogic_health` — sanity check
- `plogic_truth_table(ctrl: number[], out_csv?)`
- `plogic_cascade(threshold, beta, xpm_mode, n2?, a_eff?, n_eff?, g_geom?, extra?: string[])`
- `plogic_sweep_parallel(configs: {...}[])`
- `plogic_bo_run(n_calls?, threshold?, xpm_mode?, space_bounds?, fixed_params?, objective_margin_weight?, random_starts?)`
- `plogic_schema` — capability ping

## Runbook
1) Ensure `external/photonic-logic` submodule is present and/or package is installed.
2) `docker-compose up -d` (override picked automatically)
3) (Optional) call registry loader wherever your registry is built:
   ```python
   from mcp_agent.registry_loader import load_and_register_from_file
   load_and_register_from_file(registry, "config/tools.yaml")
   ```
4) CI will validate: JSON + CSV → health → truth-table(3) → tiny BO(4)
5) Inspect persisted results in `/data/plogic_results`

## Notes
- GP-BO via scikit-optimize if installed; otherwise random search fallback.
- LRU+TTL cache; Redis used if `REDIS_URL` is set.
- Timeouts are enforced; tune via env if needed.
