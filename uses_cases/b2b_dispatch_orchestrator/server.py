"""
B2B Use Case: Field Dispatch Orchestrator

Run:
  python use_cases/b2b_dispatch_orchestrator/server.py
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from polymcp import expose_tools_http

WORK_ORDERS: Dict[str, Dict[str, Any]] = {}
TECHNICIANS: List[Dict[str, Any]] = [
    {"tech_id": "tech_01", "skills": ["electrical", "network"], "active_jobs": 1},
    {"tech_id": "tech_02", "skills": ["hvac", "electrical"], "active_jobs": 0},
    {"tech_id": "tech_03", "skills": ["network", "security"], "active_jobs": 2},
]


def create_work_order(site_id: str, issue_type: str, severity: str = "medium") -> Dict[str, Any]:
    """Create a field service work order with SLA deadline."""
    work_order_id = f"WO-{len(WORK_ORDERS) + 1:04d}"
    sev = severity.lower()
    sla_hours = 4 if sev == "critical" else (8 if sev == "high" else 24)
    due_at = (datetime.utcnow() + timedelta(hours=sla_hours)).isoformat() + "Z"

    order = {
        "work_order_id": work_order_id,
        "site_id": site_id,
        "issue_type": issue_type.lower(),
        "severity": sev,
        "status": "open",
        "assigned_technician": None,
        "sla_due_at": due_at,
    }
    WORK_ORDERS[work_order_id] = order
    return order


def assign_best_technician(work_order_id: str) -> Dict[str, Any]:
    """Assign the least-loaded technician with matching skill."""
    order = WORK_ORDERS.get(work_order_id)
    if not order:
        raise ValueError(f"Unknown work_order_id: {work_order_id}")

    issue_type = order["issue_type"]
    candidates = [t for t in TECHNICIANS if issue_type in t["skills"]]
    if not candidates:
        candidates = TECHNICIANS[:]

    best = sorted(candidates, key=lambda t: (t["active_jobs"], t["tech_id"]))[0]
    best["active_jobs"] += 1
    order["assigned_technician"] = best["tech_id"]
    order["status"] = "assigned"

    return {
        "work_order_id": work_order_id,
        "assigned_technician": best["tech_id"],
        "active_jobs_after_assignment": best["active_jobs"],
        "status": order["status"],
    }


def check_sla_risk(work_order_id: str) -> Dict[str, Any]:
    """Estimate if the work order is at SLA risk based on severity and status."""
    order = WORK_ORDERS.get(work_order_id)
    if not order:
        raise ValueError(f"Unknown work_order_id: {work_order_id}")

    risk = "low"
    if order["severity"] in {"critical", "high"} and order["status"] != "assigned":
        risk = "high"
    elif order["severity"] == "medium" and order["status"] == "open":
        risk = "medium"

    return {
        "work_order_id": work_order_id,
        "severity": order["severity"],
        "status": order["status"],
        "sla_risk": risk,
        "sla_due_at": order["sla_due_at"],
    }


def dispatch_summary() -> Dict[str, Any]:
    """Return summary of current dispatch state."""
    open_orders = [o for o in WORK_ORDERS.values() if o["status"] == "open"]
    assigned_orders = [o for o in WORK_ORDERS.values() if o["status"] == "assigned"]
    return {
        "total_orders": len(WORK_ORDERS),
        "open_orders": len(open_orders),
        "assigned_orders": len(assigned_orders),
        "technician_loads": [{k: t[k] for k in ("tech_id", "active_jobs")} for t in TECHNICIANS],
    }


app = expose_tools_http(
    tools=[create_work_order, assign_best_technician, check_sla_risk, dispatch_summary],
    title="Dispatch Orchestrator MCP Server",
    description="B2B field dispatch tools over MCP HTTP",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8102)
