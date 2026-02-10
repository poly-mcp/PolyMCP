"""
Smoke test for B2B support copilot use case.

Requires server running on:
  http://127.0.0.1:8101
"""

import json

import requests

BASE = "http://127.0.0.1:8101/mcp"


def invoke(tool_name: str, payload: dict) -> dict:
    response = requests.post(f"{BASE}/invoke/{tool_name}", json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


def main() -> None:
    created = invoke(
        "create_ticket",
        {
            "customer_id": "cust_123",
            "subject": "Refund requested after duplicate charge",
            "body": "I was charged twice for order #A-9912",
            "priority": "high",
        },
    )
    ticket_id = created["result"]["ticket_id"]

    classified = invoke("classify_ticket", {"ticket_id": ticket_id})
    resolution = invoke("suggest_resolution", {"ticket_id": ticket_id})
    closed = invoke(
        "close_ticket",
        {"ticket_id": ticket_id, "resolution_note": "Refund approved and confirmation email sent."},
    )

    print(json.dumps({"created": created, "classified": classified, "resolution": resolution, "closed": closed}, indent=2))


if __name__ == "__main__":
    main()
