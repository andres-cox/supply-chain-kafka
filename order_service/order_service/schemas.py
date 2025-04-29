"""Kafka producer for publishing order events."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderItem(BaseModel):
    """Represents an individual item in an order.

    Attributes:
        sku (str): Stock Keeping Unit identifier, must be alphanumeric with optional hyphens.
        quantity (int): Number of items ordered, must be between 1 and 1000.
        price (float): Price per unit in USD, must be positive.
    """

    sku: str = Field(..., min_length=3, max_length=50)
    quantity: int = Field(..., gt=0, le=1000)
    price: float = Field(..., gt=0, description="USD price per unit")

    @field_validator("sku")
    def validate_sku(cls, v):
        """Validate and normalize SKU format.

        Args:
            v (str): SKU value to validate.

        Returns:
            str: Uppercase normalized SKU.

        Raises:
            ValueError: If SKU contains invalid characters.
        """
        if not v.replace("-", "").isalnum():
            raise ValueError("SKU must be alphanumeric with optional hyphens")
        return v.upper()

    model_config = ConfigDict(
        json_schema_extra={
            "properties": {
                "sku": {"example": "PROD-001"},
                "quantity": {"example": 2},
                "price": {"example": 9.99},
            }
        }
    )


class OrderSchema(BaseModel):
    """Represents a complete order in the system.

    Attributes:
        order_id (str): Unique order identifier, auto-generated if not provided.
        customer_id (str): Customer identifier, minimum 5 characters.
        items (list[OrderItem]): List of items in the order, at least one required.
        status (str): Order status, one of: pending, processed, cancelled.
        created_at (datetime): Timestamp when the order was created.
    """

    order_id: str = Field(
        default_factory=lambda: f"ord-{uuid.uuid4().hex[:8]}", description="Unique order identifier"
    )
    customer_id: str = Field(..., min_length=5)
    items: list[OrderItem] = Field(..., min_length=1, description="At least one item required")
    status: Literal["pending", "processed", "cancelled"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow, exclude=True)

    @classmethod
    def model_serializer(cls, obj):
        """Serialize model to dictionary format.

        Args:
            obj: The OrderSchema instance to serialize.

        Returns:
            dict: Serialized order data with ISO formatted datetime.
        """
        data = obj.model_dump()
        if "created_at" in data:
            data["created_at"] = data["created_at"].isoformat()
        return data

    model_config = ConfigDict(
        json_schema_extra={
            "properties": {
                "customer_id": {"example": "cust-12345"},
                "items": {
                    "example": [
                        {"sku": "PROD-001", "quantity": 2, "price": 9.99},
                        {"sku": "PROD-002", "quantity": 1, "price": 24.95},
                    ]
                },
            }
        }
    )
