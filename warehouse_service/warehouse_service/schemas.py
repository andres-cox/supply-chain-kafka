"""Pydantic models for Warehouse Service order payloads."""

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    """Represents a single item in an order."""

    sku: str = Field(..., description="The SKU (product ID) of the item.")
    quantity: int = Field(..., ge=1, description="Number of units ordered.")
    price: float = Field(..., ge=0, description="Price per unit.")


class OrderPayload(BaseModel):
    """Represents the full order structure consumed from Kafka."""

    order_id: str = Field(..., description="Unique identifier for the order.")
    items: list[OrderItem] = Field(..., description="List of order items.")
    customer_id: str = Field(..., description="Customer who placed the order.")
    created_at: str = Field(..., description="Timestamp when the order was created.")
