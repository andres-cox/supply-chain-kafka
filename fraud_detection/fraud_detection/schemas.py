"""Schemas for fraud detection service data models."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class LocationData(BaseModel):
    """Location data for fraud detection.

    Attributes:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        timestamp: When the location was recorded
    """

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FraudAlert(BaseModel):
    """Represents a fraud alert in the system.

    Attributes:
        alert_id: Unique identifier for the alert
        order_id: Reference to the original order
        customer_id: Customer identifier
        alert_type: Type of fraud detected
        confidence_score: Probability score of fraud (0-1)
        details: Additional information about the fraud
        created_at: When the alert was generated
    """

    alert_id: str = Field(
        default_factory=lambda: f"fraud-{datetime.utcnow().strftime('%Y%m%d')}-{hash(datetime.utcnow())}"[
            -8:
        ],
        description="Unique alert identifier",
    )
    order_id: str = Field(..., description="Reference to the original order")
    customer_id: str = Field(..., min_length=5)
    alert_type: Literal["unusual_route", "rapid_location_change", "known_fraud_pattern", "suspicious_timing"]
    confidence_score: float = Field(..., ge=0, le=1)
    details: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    location_data: LocationData

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "order_id": "ord-12345678",
                "customer_id": "cust-12345",
                "alert_type": "unusual_route",
                "confidence_score": 0.85,
                "details": "Shipment route deviates significantly from expected path",
                "location_data": {
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "timestamp": "2025-04-30T12:00:00Z",
                },
            }
        }
    )

    @classmethod
    def model_serializer(cls, obj):
        """Serialize model to dictionary format.

        Args:
            obj: The FraudAlert instance to serialize

        Returns:
            dict: Serialized fraud alert data with ISO formatted datetime
        """
        data = obj.model_dump()
        data["created_at"] = data["created_at"].isoformat()
        data["location_data"]["timestamp"] = data["location_data"]["timestamp"].isoformat()
        return data
