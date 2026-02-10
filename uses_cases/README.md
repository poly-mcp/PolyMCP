# PolyMCP Runnable Use Cases (B2B + B2C)

This folder contains 3 runnable demos with real MCP tools, HTTP endpoints, and smoke tests.

Each use case includes:
- `server.py`: MCP tool server
- `smoke_test.py`: quick end-to-end validation
- `README.md`: local run instructions

## Prerequisites

```bash
pip install polymcp requests uvicorn
```

## 1) B2B Support Copilot

Folder:
- `use_cases/b2b_support_copilot/`

Run:
```bash
python use_cases/b2b_support_copilot/server.py
```

Endpoint:
- `http://127.0.0.1:8101/mcp`

Smoke test:
```bash
python use_cases/b2b_support_copilot/smoke_test.py
```

Tools covered:
- `create_ticket`
- `classify_ticket`
- `suggest_resolution`
- `close_ticket`

## 2) B2B Dispatch Orchestrator

Folder:
- `use_cases/b2b_dispatch_orchestrator/`

Run:
```bash
python use_cases/b2b_dispatch_orchestrator/server.py
```

Endpoint:
- `http://127.0.0.1:8102/mcp`

Smoke test:
```bash
python use_cases/b2b_dispatch_orchestrator/smoke_test.py
```

Tools covered:
- `create_work_order`
- `assign_best_technician`
- `check_sla_risk`
- `dispatch_summary`

## 3) B2C Ecommerce Assistant

Folder:
- `use_cases/b2c_ecommerce_assistant/`

Run:
```bash
python use_cases/b2c_ecommerce_assistant/server.py
```

Endpoint:
- `http://127.0.0.1:8103/mcp`

Smoke test:
```bash
python use_cases/b2c_ecommerce_assistant/smoke_test.py
```

Tools covered:
- `create_order`
- `get_order_status`
- `recommend_upsell`
- `request_return`

## Optional: Test with PolyMCP CLI + Agent

With one or more servers running:

```bash
polymcp server add http://127.0.0.1:8101/mcp --name support-demo
polymcp server add http://127.0.0.1:8102/mcp --name dispatch-demo
polymcp server add http://127.0.0.1:8103/mcp --name ecommerce-demo

polymcp server list
polymcp agent run
```

## Notes

- These demos use in-memory data stores (no database).
- They are intentionally simple and designed for experimentation and demos.
- For production, add persistence, auth, rate limits, and audit logging.
