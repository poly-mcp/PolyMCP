"""
B2B Use Case: Customer Support Operations Copilot

Run:
  python use_cases/b2b_support_copilot/server.py
"""

from typing import Any, Dict

from polymcp import expose_tools_http

TICKETS: Dict[str, Dict[str, Any]] = {}
KB_BY_CATEGORY = {
    "billing": "Ask for order_id and payment proof, then offer refund or invoice correction.",
    "technical": "Collect environment details, reproduce issue, and provide workaround + fix ETA.",
    "shipping": "Check shipment status, carrier SLA, and offer replacement if package is lost.",
    "general": "Clarify user intent, gather missing data, and route to the correct queue.",
}


def create_ticket(customer_id: str, subject: str, body: str, priority: str = "normal") -> Dict[str, Any]:
    """Create a support ticket."""
    ticket_id = f"T-{len(TICKETS) + 1:04d}"
    ticket = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "subject": subject,
        "body": body,
        "priority": priority.lower(),
        "status": "open",
        "category": "unclassified",
    }
    TICKETS[ticket_id] = ticket
    return ticket


def classify_ticket(ticket_id: str) -> Dict[str, Any]:
    """Classify a support ticket by keyword rules."""
    ticket = TICKETS.get(ticket_id)
    if not ticket:
        raise ValueError(f"Unknown ticket_id: {ticket_id}")

    text = f"{ticket['subject']} {ticket['body']}".lower()
    if any(k in text for k in ("refund", "invoice", "billing", "payment")):
        category = "billing"
    elif any(k in text for k in ("error", "bug", "crash", "500", "timeout")):
        category = "technical"
    elif any(k in text for k in ("shipping", "delivery", "tracking", "courier")):
        category = "shipping"
    else:
        category = "general"

    ticket["category"] = category
    return {
        "ticket_id": ticket_id,
        "category": category,
        "status": ticket["status"],
    }


def suggest_resolution(ticket_id: str) -> Dict[str, Any]:
    """Return a suggested resolution plan for the ticket category."""
    ticket = TICKETS.get(ticket_id)
    if not ticket:
        raise ValueError(f"Unknown ticket_id: {ticket_id}")

    category = ticket.get("category", "general")
    return {
        "ticket_id": ticket_id,
        "category": category,
        "playbook": KB_BY_CATEGORY.get(category, KB_BY_CATEGORY["general"]),
        "next_action": "reply_to_customer",
    }


def close_ticket(ticket_id: str, resolution_note: str) -> Dict[str, Any]:
    """Close a support ticket with a resolution note."""
    ticket = TICKETS.get(ticket_id)
    if not ticket:
        raise ValueError(f"Unknown ticket_id: {ticket_id}")

    ticket["status"] = "closed"
    ticket["resolution_note"] = resolution_note
    return {
        "ticket_id": ticket_id,
        "status": ticket["status"],
        "resolution_note": resolution_note,
    }


app = expose_tools_http(
    tools=[create_ticket, classify_ticket, suggest_resolution, close_ticket],
    title="Support Copilot MCP Server",
    description="B2B support workflow tools over MCP HTTP",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8101)
