"""Kafka consumer for processing order tracking events."""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Callable, Awaitable
import traceback

from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_utils.config import get_kafka_logger

from tracking_service.schemas import (
    PREDEFINED_LOCATIONS,
    ROUTES,
    Location,
    ShipmentPriority,
    TrackingEvent,
    TrackingItem,
)

logger = get_kafka_logger("tracking-service")


class TrackingConsumer:
    """Consumer for processing order tracking events from Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
    ) -> None:
        """Initialize the tracking consumer."""
        logger.info(
            f"Initializing consumer | bootstrap_servers={bootstrap_servers} | group_id={group_id}"
        )
        self.consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": enable_auto_commit,
            }
        )

    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to the specified Kafka topics."""
        logger.info(f"Subscribing to topics: {topics}")
        self.consumer.subscribe(topics)
        logger.info("Successfully subscribed to topics")

    def _calculate_estimated_delivery(self, priority: ShipmentPriority) -> datetime:
        """Calculate estimated delivery time based on priority."""
        route = ROUTES["express" if priority in [ShipmentPriority.EXPRESS, ShipmentPriority.HIGH] else "standard"]
        # Demo values: 2 hours per hop for standard, less for higher priorities
        hours_per_hop = {
            ShipmentPriority.STANDARD: 2,
            ShipmentPriority.HIGH: 1.5,
            ShipmentPriority.EXPRESS: 1
        }
        total_hours = len(route) * hours_per_hop[priority]
        return datetime.utcnow() + timedelta(hours=total_hours)

    async def process_messages(self, handler: Callable[[TrackingEvent], Awaitable[None]]) -> None:
        """Process incoming messages continuously (async)."""
        logger.info("Starting message processing loop (async)")
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    await asyncio.sleep(0.1)
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition")
                        continue
                    logger.error(f"Kafka error: {msg.error()}")
                    raise KafkaException(msg.error())

                try:
                    # Parse message value
                    value_str = msg.value().decode("utf-8")
                    value = json.loads(value_str)
                    logger.debug(f"Received message: {value_str}")

                    # Determine priority (demo: 20% express, 30% high, 50% standard)
                    if "priority" in value:
                        priority = ShipmentPriority(value["priority"])
                    else:
                        order_num = int(value["order_id"].split("-")[1], 16)
                        if order_num % 10 < 2:  # 20% express
                            priority = ShipmentPriority.EXPRESS
                        elif order_num % 10 < 5:  # 30% high
                            priority = ShipmentPriority.HIGH
                        else:  # 50% standard
                            priority = ShipmentPriority.STANDARD

                    # Convert order data to tracking items
                    tracking_items = []
                    for item in value.get("items", []):
                        try:
                            tracking_item = TrackingItem(
                                sku=item.get("sku"),
                                quantity=item.get("quantity", 1),
                                price=item.get("price", 0.0),
                                status="received",
                                location=PREDEFINED_LOCATIONS["start"]
                            )
                            tracking_items.append(tracking_item)
                        except Exception as item_error:
                            logger.error(
                                f"Failed to process item in order | error={item_error} | item_data={item} | order_id={value.get('order_id')}"
                            )

                    # Set up route based on priority
                    route_type = "express" if priority in [ShipmentPriority.EXPRESS, ShipmentPriority.HIGH] else "standard"
                    route_checkpoints = ROUTES[route_type]

                    # Create tracking event
                    tracking_event = TrackingEvent(
                        order_id=value["order_id"],
                        customer_id=value["customer_id"],
                        items=tracking_items,
                        event_type="order_received",
                        current_location=PREDEFINED_LOCATIONS["start"],
                        next_location=PREDEFINED_LOCATIONS[route_checkpoints[1]],
                        route_checkpoints=route_checkpoints,
                        current_checkpoint=0,
                        priority=priority,
                        estimated_delivery=self._calculate_estimated_delivery(priority)
                    )

                    logger.info(
                        f"Created tracking event | order_id={tracking_event.order_id} | customer_id={tracking_event.customer_id} | "
                        f"priority={priority.value} | route_type={route_type} | num_stops={len(route_checkpoints)}"
                    )

                    # Handle the event
                    await handler(tracking_event)

                    # Process the message (simulate update)
                    logger.info(
                        f"Successfully processed tracking event | tracking_id={getattr(tracking_event, 'tracking_id', None)} | "
                        f"current_location={tracking_event.current_location.name} | "
                        f"next_location={tracking_event.next_location.name if tracking_event.next_location else None} | "
                        f"checkpoint={tracking_event.current_checkpoint}/{len(tracking_event.route_checkpoints)} | "
                        f"priority={tracking_event.priority.value} | topic={msg.topic()} | partition={msg.partition()} | offset={msg.offset()}"
                    )

                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to decode message | error={e} | raw_message={value_str if 'value_str' in locals() else None} | "
                        f"topic={msg.topic()} | partition={msg.partition()} | offset={msg.offset()}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message | error={e} | error_type={type(e).__name__} | "
                        f"message_data={value if 'value' in locals() else None} | "
                        f"traceback={traceback.format_exc()} | topic={msg.topic()} | partition={msg.partition()} | offset={msg.offset()}"
                    )

        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        finally:
            self.close()

    def close(self) -> None:
        """Close the consumer connection."""
        self.consumer.close()
        logger.info("Consumer closed")
