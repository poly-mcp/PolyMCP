"""
Smoke test for B2B dispatch orchestrator use case.

Requires server running on:
  http://127.0.0.1:8102
"""

import json
from typing import Any, Dict, Optional

import requests

BASE = "http://127.0.0.1:8102/mcp"


def invoke(tool_name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = payload or {}
    response = requests.post(f"{BASE}/invoke/{tool_name}", json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


def main() -> None:
    created = invoke(
        "create_work_order",
        {"site_id": "site_nyc_42", "issue_type": "electrical", "severity": "high"},
    )
    work_order_id = created["result"]["work_order_id"]

    assigned = invoke("assign_best_technician", {"work_order_id": work_order_id})
    risk = invoke("check_sla_risk", {"work_order_id": work_order_id})
    summary = invoke("dispatch_summary")

    print(json.dumps({"created": created, "assigned": assigned, "risk": risk, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
