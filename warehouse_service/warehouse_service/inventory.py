"""Kafka producer for publishing order events."""

from .logger import logger
from .schemas import OrderPayload


def process_order(order: dict) -> None:
    """Process an incoming order and attempt inventory allocation.

    Args:
        order (dict): Raw order dictionary from Kafka.
    """
    parsed = OrderPayload(**order)
    logger.info(f"Allocating inventory for order: {parsed.order_id}")
    for item in parsed.items:
        logger.info(f"  - {item.quantity}x {item.sku} at ${item.price}")
