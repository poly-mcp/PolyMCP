# B2B Dispatch Orchestrator (Runnable Demo)

## Start server

```bash
python use_cases/b2b_dispatch_orchestrator/server.py
```

Server endpoint:
- `http://127.0.0.1:8102/mcp`

## Run smoke test

```bash
python use_cases/b2b_dispatch_orchestrator/smoke_test.py
```

What it tests:
1. create work order
2. assign technician
3. check SLA risk
4. dispatch summary
