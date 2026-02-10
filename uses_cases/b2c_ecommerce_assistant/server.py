"""
B2C Use Case: Ecommerce Assistant + Ops Bridge

Run:
  python use_cases/b2c_ecommerce_assistant/server.py
"""

from typing import Any, Dict, List

from polymcp import expose_tools_http

CATALOG: Dict[str, Dict[str, Any]] = {
    "sku_keyboard": {"name": "Mechanical Keyboard", "price": 129.0, "upsell": "sku_wrist_rest"},
    "sku_mouse": {"name": "Wireless Mouse", "price": 59.0, "upsell": "sku_mousepad"},
    "sku_headset": {"name": "Gaming Headset", "price": 99.0, "upsell": "sku_stand"},
    "sku_wrist_rest": {"name": "Wrist Rest", "price": 19.0, "upsell": None},
    "sku_mousepad": {"name": "Mousepad XL", "price": 29.0, "upsell": None},
    "sku_stand": {"name": "Headset Stand", "price": 24.0, "upsell": None},
}
ORDERS: Dict[str, Dict[str, Any]] = {}


def create_order(customer_id: str, items: List[str]) -> Dict[str, Any]:
    """Create an order and compute total amount."""
    if not items:
        raise ValueError("items must contain at least one sku")

    unknown = [sku for sku in items if sku not in CATALOG]
    if unknown:
        raise ValueError(f"Unknown sku(s): {unknown}")

    order_id = f"O-{len(ORDERS) + 1:05d}"
    total = round(sum(float(CATALOG[sku]["price"]) for sku in items), 2)

    order = {
        "order_id": order_id,
        "customer_id": customer_id,
        "items": items,
        "status": "processing",
        "total": total,
        "tracking_code": f"TRK-{order_id}",
        "return_status": "none",
    }
    ORDERS[order_id] = order
    return order


def get_order_status(order_id: str) -> Dict[str, Any]:
    """Get order and delivery status."""
    order = ORDERS.get(order_id)
    if not order:
        raise ValueError(f"Unknown order_id: {order_id}")
    return {
        "order_id": order_id,
        "status": order["status"],
        "tracking_code": order["tracking_code"],
        "total": order["total"],
    }


def request_return(order_id: str, reason: str) -> Dict[str, Any]:
    """Create a return request for an order."""
    order = ORDERS.get(order_id)
    if not order:
        raise ValueError(f"Unknown order_id: {order_id}")

    order["return_status"] = "requested"
    order["return_reason"] = reason
    return {
        "order_id": order_id,
        "return_status": order["return_status"],
        "next_step": "customer_receive_return_label",
    }


def recommend_upsell(order_id: str) -> Dict[str, Any]:
    """Recommend an upsell product based on ordered items."""
    order = ORDERS.get(order_id)
    if not order:
        raise ValueError(f"Unknown order_id: {order_id}")

    for sku in order["items"]:
        upsell_sku = CATALOG[sku].get("upsell")
        if upsell_sku:
            return {
                "order_id": order_id,
                "recommended_sku": upsell_sku,
                "recommended_product": CATALOG[upsell_sku]["name"],
                "recommended_price": CATALOG[upsell_sku]["price"],
            }

    return {"order_id": order_id, "recommended_sku": None, "message": "No upsell recommendation."}


app = expose_tools_http(
    tools=[create_order, get_order_status, request_return, recommend_upsell],
    title="Ecommerce Assistant MCP Server",
    description="B2C ecommerce and operations bridge tools over MCP HTTP",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8103)
