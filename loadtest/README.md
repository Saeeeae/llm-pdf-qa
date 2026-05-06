# Load Testing — RAG-LLM

Locust scenarios. Run from the host (locust is not part of the docker stack).

## Prerequisites

```bash
pip install locust pandas matplotlib
```

## Environment Variables

| Variable    | Default      | Description                  |
|-------------|--------------|------------------------------|
| `LOAD_JWT`  | `test-token` | Bearer token for API calls   |
| `LOAD_HOST` | —            | Target base URL              |

## Scenarios

### Sustained (30 min, 100 users)

```bash
locust -f loadtest/locustfile.py --host=$LOAD_HOST \
  -u 100 -r 10 -t 30m --headless --csv=loadtest/results/sustained
```

### Spike (0 → 200 over 30 s)

```bash
locust -f loadtest/scenarios/spike.py --host=$LOAD_HOST \
  --headless --csv=loadtest/results/spike
```

> Note: previous Make targets `make load-test` / `make load-spike` were
> retired in the docker-only Makefile refactor. Run locust directly as
> shown above. Target the gateway (`http://localhost:8080`) for end-to-end
> measurement, or a specific module port for isolation.

## Analyze Results

```bash
python loadtest/analyze.py loadtest/results/sustained
# produces: loadtest/results/sustained_latency.png
```

## Task Mix

| Endpoint            | Weight | Notes                       |
|---------------------|--------|-----------------------------|
| `POST /api/v1/chat` | 70%    | Main RAG query              |
| `GET /api/v1/admin/users` | 20% | Admin user list           |
| `GET /health`       | 10%    | Health probe                |

## Target SLOs (production: 100 concurrent, 200 qpm)

| Metric        | Target  |
|---------------|---------|
| p50 latency   | < 500 ms |
| p95 latency   | < 2 s    |
| p99 latency   | < 3 s    |
| Error rate    | < 1%     |

## Output Files

Results land in `loadtest/results/` (git-ignored except `.gitkeep`):

- `*_stats.csv` — per-endpoint summary
- `*_stats_history.csv` — time-series data
- `*_failures.csv` — failure log
- `*_latency.png` — chart produced by `analyze.py`
