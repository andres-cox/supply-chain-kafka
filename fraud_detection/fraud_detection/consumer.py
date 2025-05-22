"""Kafka consumer for processing orders and location updates."""

import json
from datetime import datetime
from typing import Callable
import math
from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_utils.config import get_kafka_logger

from .schemas import FraudAlert, LocationData

logger = get_kafka_logger("fraud-detection")


class FraudDetectionConsumer:
    """Consumer for processing orders and location updates for fraud detection."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
    ):
        """Initialize the fraud detection consumer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            group_id: Consumer group ID
            auto_offset_reset: Where to start consuming from if no offset is stored
            enable_auto_commit: Whether to auto-commit offsets
        """
        logger.info(
            f"Initializing consumer with bootstrap_servers={bootstrap_servers}, " f"group_id={group_id}"
        )
        self.consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": enable_auto_commit,
            }
        )
        # Store location history for fraud detection
        self._location_history = {}

    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to the specified Kafka topics.

        Args:
            topics: List of topic names to subscribe to
        """
        logger.info(f"Subscribing to topics: {topics}")
        self.consumer.subscribe(topics)
        logger.info("Successfully subscribed to topics")

    def process_messages(self, alert_handler: Callable[[FraudAlert], None]) -> None:
        """Process incoming messages continuously.

        Args:
            alert_handler: Callback function to handle fraud alerts
        """
        logger.info("Starting message processing loop")
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition")
                        continue
                    logger.error(f"Kafka error: {msg.error()}")
                    raise KafkaException(msg.error())

                try:
                    # Log raw message for debugging
                    value_str = msg.value().decode("utf-8")
                    logger.debug(f"Received message: {value_str}")

                    # Parse message value
                    value = json.loads(value_str)

                    # Process based on topic
                    topic = msg.topic()
                    if topic == "orders.created":
                        self._process_order(value)
                    elif topic == "location.updates":
                        self._process_location_update(value, alert_handler)

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)

        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        finally:
            self.consumer.close()

    def _process_order(self, order_data: dict) -> None:
        """Process a new order event.

        Args:
            order_data: Raw order data from Kafka
        """
        order_id = order_data.get("order_id")
        if order_id:
            # Initialize location history for the order
            self._location_history[order_id] = []
            logger.info(f"Initialized tracking for order: {order_id}")

    def _process_location_update(
        self, location_data: dict, alert_handler: Callable[[FraudAlert], None]
    ) -> None:
        """Process a location update and check for suspicious patterns.

        Args:
            location_data: Location update data from Kafka
            alert_handler: Callback to handle generated fraud alerts
        """
        order_id = location_data.get("order_id")
        if not order_id or order_id not in self._location_history:
            logger.warning(f"Received location update for unknown order: {order_id}")
            return

        # Create LocationData instance
        location = LocationData(
            latitude=location_data["latitude"],
            longitude=location_data["longitude"],
            timestamp=datetime.fromisoformat(location_data["timestamp"]),
        )

        # Add to history
        self._location_history[order_id].append(location)
        history = self._location_history[order_id]

        # Check for suspicious patterns if we have enough history
        if len(history) >= 2:
            self._check_rapid_movement(order_id, history[-2], history[-1], location_data, alert_handler)

    def _check_rapid_movement(
        self,
        order_id: str,
        prev_location: LocationData,
        curr_location: LocationData,
        location_data: dict,
        alert_handler: Callable[[FraudAlert], None],
    ) -> None:
        """Check for suspiciously rapid movement between locations.

        Args:
            order_id: The order being tracked
            prev_location: Previous location data
            curr_location: Current location data
            location_data: Raw location update data
            alert_handler: Callback to handle generated fraud alerts
        """
        # Calculate distance and time difference
        distance = self._calculate_distance(
            prev_location.latitude, prev_location.longitude, curr_location.latitude, curr_location.longitude
        )
        time_diff = (curr_location.timestamp - prev_location.timestamp).total_seconds()

        # Calculate speed in km/h
        if time_diff > 0:
            speed = (distance / time_diff) * 3600  # Convert to km/h

            # Alert if speed is over 150 km/h (adjust threshold as needed)
            if speed > 150:
                alert = FraudAlert(
                    order_id=order_id,
                    customer_id=location_data["customer_id"],
                    alert_type="rapid_location_change",
                    confidence_score=min(speed / 200, 1.0),  # Scale confidence with speed
                    details=f"Suspicious movement speed: {speed:.2f} km/h",
                    location_data=curr_location,
                )
                alert_handler(alert)

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers.

        Args:
            lat1: Latitude of first point
            lon1: Longitude of first point
            lat2: Latitude of second point
            lon2: Longitude of second point

        Returns:
            float: Distance in kilometers
        """
        R = 6371  # Earth's radius in kilometers

        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        return R * c

    def close(self) -> None:
        """Close the consumer connection."""
        self.consumer.close()
        logger.info("Consumer closed")
