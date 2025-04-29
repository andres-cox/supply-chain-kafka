"""Test fixtures for the order service tests."""

import pytest

from order_service.producer import OrderProducer
from order_service.schemas import OrderItem, OrderSchema


@pytest.fixture
def test_order():
    """Create a test order fixture.

    Returns:
        OrderSchema: A sample order with a test customer and one item.
    """
    return OrderSchema(customer_id="test_cust", items=[OrderItem(sku="TEST-001", quantity=1, price=10.0)])


@pytest.fixture
def test_producer():
    """Create a test Kafka producer fixture.

    Returns:
        OrderProducer: A configured producer instance pointing to localhost.
    """
    return OrderProducer("localhost:9092")
