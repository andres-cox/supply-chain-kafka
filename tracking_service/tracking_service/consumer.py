"""Kafka consumer for processing order tracking events."""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_utils.config import get_kafka_logger

from tracking_service.schemas import (PREDEFINED_LOCATIONS, Location,
                                   ShipmentPriority, TrackingEvent, TrackingItem)

# Configure Kafka-specific logger
logger = get_kafka_logger("tracking-service")

# Update intervals in seconds (reduced for demo purposes)
UPDATE_INTERVALS = {
    ShipmentPriority.STANDARD: 60,  # Every minute
    ShipmentPriority.HIGH: 30,      # Every 30 seconds
    ShipmentPriority.EXPRESS: 15,    # Every 15 seconds
}

class TrackingConsumer:
    """Consumer for processing order tracking events from Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
    ):
        """Initialize the tracking consumer."""
        logger.info(
            f"Initializing consumer with bootstrap_servers={bootstrap_servers}, "
            f"group_id={group_id}"
        )
        self.consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": enable_auto_commit,
            }
        )
        self._active_shipments = {}
        self._stop_flag = threading.Event()
        self._location_updater = None

    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to the specified Kafka topics."""
        logger.info(f"Subscribing to topics: {topics}")
        self.consumer.subscribe(topics)
        logger.info("Successfully subscribed to topics")

        # Start location update thread
        self._location_updater = threading.Thread(
            target=self._update_locations,
            daemon=True
        )
        self._location_updater.start()

    def _determine_priority(self, order_data: dict) -> ShipmentPriority:
        """Determine shipment priority based on order data."""
        total_value = sum(item.get("price", 0) * item.get("quantity", 0) 
                         for item in order_data.get("items", []))
        
        if total_value >= 1000:
            return ShipmentPriority.EXPRESS
        elif total_value >= 500:
            return ShipmentPriority.HIGH
        return ShipmentPriority.STANDARD

    def _update_locations(self):
        """Background thread to update shipment locations."""
        while not self._stop_flag.is_set():
            try:
                current_time = time.time()
                for order_id, shipment in list(self._active_shipments.items()):
                    tracking_event = shipment["event"]
                    last_update = shipment["last_update"]
                    route = shipment["route"]
                    current_idx = shipment["route_index"]
                    update_interval = UPDATE_INTERVALS[tracking_event.priority]

                    if current_time - last_update >= update_interval:
                        # Move to next location if enough time has passed
                        if current_idx < len(route) - 1:
                            current_idx += 1
                            tracking_event.current_location = route[current_idx]
                            
                            # Update status based on location
                            new_status = "in_transit"
                            if current_idx == len(route) - 1:
                                new_status = "delivered"
                            elif current_idx == len(route) - 2:
                                new_status = "out_for_delivery"
                            
                            for item in tracking_event.items:
                                item.status = new_status
                                item.location = tracking_event.current_location
                                item.timestamp = datetime.utcnow()

                            tracking_event.event_type = "location_update"
                            if new_status == "delivered":
                                tracking_event.event_type = "delivery_complete"
                                del self._active_shipments[order_id]

                            # Call handler with updated event
                            shipment["handler"](tracking_event)
                            
                            if order_id in self._active_shipments:
                                self._active_shipments[order_id]["last_update"] = current_time
                                self._active_shipments[order_id]["route_index"] = current_idx

            except Exception as e:
                logger.error(f"Error updating locations: {e}", exc_info=True)
            
            time.sleep(5)  # Check every 5 seconds

    def process_messages(self, handler: Callable[[TrackingEvent], None]) -> None:
        """Process incoming messages continuously."""
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
                    # Parse and process message
                    value_str = msg.value().decode("utf-8")
                    value = json.loads(value_str)
                    logger.debug(f"Received order: {value['order_id']}")

                    # Determine priority and create tracking items
                    priority = self._determine_priority(value)
                    tracking_items = [
                        TrackingItem(
                            sku=item["sku"],
                            quantity=item["quantity"],
                            price=item["price"],
                            status="processing",
                            location=PREDEFINED_LOCATIONS["start"]
                        )
                        for item in value.get("items", [])
                    ]

                    # Calculate route based on priority
                    route = (
                        [PREDEFINED_LOCATIONS["start"], PREDEFINED_LOCATIONS["final"]]
                        if priority == ShipmentPriority.EXPRESS
                        else [PREDEFINED_LOCATIONS["start"], PREDEFINED_LOCATIONS["dc1"],
                             PREDEFINED_LOCATIONS["final"]]
                    )

                    # Create initial tracking event
                    tracking_event = TrackingEvent(
                        order_id=value["order_id"],
                        customer_id=value["customer_id"],
                        items=tracking_items,
                        event_type="order_received",
                        priority=priority,
                        current_location=PREDEFINED_LOCATIONS["start"],
                        destination=PREDEFINED_LOCATIONS["final"],
                        estimated_delivery=datetime.utcnow() + timedelta(
                            hours=2 if priority == ShipmentPriority.EXPRESS else 4
                        )
                    )

                    # Store active shipment
                    self._active_shipments[value["order_id"]] = {
                        "event": tracking_event,
                        "route": route,
                        "route_index": 0,
                        "last_update": time.time(),
                        "handler": handler
                    }

                    # Send initial event
                    handler(tracking_event)

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)

        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        finally:
            self.close()

    def close(self) -> None:
        """Close the consumer and stop location updates."""
        self._stop_flag.set()
        if self._location_updater:
            self._location_updater.join(timeout=5)
        self.consumer.close()
        logger.info("Consumer closed")
