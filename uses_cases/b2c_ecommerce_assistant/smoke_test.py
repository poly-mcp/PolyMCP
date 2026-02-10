"""
Smoke test for B2C ecommerce assistant use case.

Requires server running on:
  http://127.0.0.1:8103
"""

import json
from typing import Any, Dict

import requests

BASE = "http://127.0.0.1:8103/mcp"


def invoke(tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(f"{BASE}/invoke/{tool_name}", json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


def main() -> None:
    created = invoke(
        "create_order",
        {
            "customer_id": "cust_b2c_01",
            "items": ["sku_keyboard", "sku_mouse"],
        },
    )
    order_id = created["result"]["order_id"]

    status = invoke("get_order_status", {"order_id": order_id})
    upsell = invoke("recommend_upsell", {"order_id": order_id})
    returned = invoke("request_return", {"order_id": order_id, "reason": "Changed my mind"})

    print(
        json.dumps(
            {
                "created": created,
                "status": status,
                "upsell": upsell,
                "return_request": returned,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
