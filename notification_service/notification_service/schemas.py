"""Schemas for notification service data models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class NotificationPreferences(BaseModel):
    """User notification preferences.

    Attributes:
        customer_id: Customer identifier
        email: Email address for notifications
        sms: Phone number for SMS notifications
        channels: Enabled notification channels
        types: Types of notifications to receive
    """

    customer_id: str = Field(..., min_length=5)
    email: EmailStr | None = None
    sms: str | None = Field(None, pattern=r"^\+[1-9]\d{1,14}$")
    channels: list[Literal["email", "sms"]] = ["email"]
    types: list[Literal["fraud_alert", "delivery_update", "delay"]] = ["fraud_alert", "delivery_update"]


class Notification(BaseModel):
    """Represents a notification to be sent.

    Attributes:
        notification_id: Unique identifier for the notification
        customer_id: Customer identifier
        type: Type of notification
        subject: Notification subject/title
        message: Notification content
        priority: Notification priority level
        created_at: When the notification was created
    """

    notification_id: str = Field(
        default_factory=lambda: f"notif-{datetime.utcnow().strftime('%Y%m%d')}-{hash(datetime.utcnow())}"[
            -8:
        ],
        description="Unique notification identifier",
    )
    customer_id: str = Field(..., min_length=5)
    type: Literal["fraud_alert", "delivery_update", "delay"]
    subject: str = Field(..., min_length=3, max_length=100)
    message: str = Field(..., min_length=10)
    priority: Literal["low", "medium", "high"] = "medium"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": "cust-12345",
                "type": "fraud_alert",
                "subject": "Suspicious Activity Detected",
                "message": "We have detected unusual movement patterns for your order #12345",
                "priority": "high",
            }
        }
    )

    @classmethod
    def model_serializer(cls, obj):
        """Serialize model to dictionary format.

        Args:
            obj: The Notification instance to serialize

        Returns:
            dict: Serialized notification data with ISO formatted datetime
        """
        data = obj.model_dump()
        data["created_at"] = data["created_at"].isoformat()
        return data
