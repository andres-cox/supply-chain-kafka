"""Tests for the tracking service components."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from confluent_kafka import Message

from tracking_service import __version__
from tracking_service.consumer import TrackingConsumer
from tracking_service.producer import TrackingProducer
from tracking_service.schemas import TrackingEvent, TrackingItem


def test_version():
    """Testing package Version."""
    assert __version__ == "0.1.0"


@pytest.fixture
def sample_order_data():
    """Fixture providing sample order data."""
    return {
        "order_id": "ord-12345678",
        "customer_id": "cust-12345",
        "items": [
            {
                "sku": "PROD-001",
                "quantity": 2,
                "price": 9.99,
            }
        ],
    }


@pytest.fixture
def sample_tracking_event():
    """Fixture providing a sample tracking event."""
    return TrackingEvent(
        order_id="ord-12345678",
        customer_id="cust-12345",
        items=[TrackingItem(sku="PROD-001", quantity=2, price=9.99, status="received")],
        event_type="order_received",
        created_at=datetime.utcnow(),
    )


def test_tracking_consumer_init():
    """Test TrackingConsumer initialization."""
    consumer = TrackingConsumer(
        bootstrap_servers="localhost:9092", group_id="test-group"
    )
    assert consumer.consumer is not None


@patch("tracking_service.consumer.Consumer")
def test_tracking_consumer_subscribe(mock_kafka_consumer):
    """Test topic subscription."""
    consumer = TrackingConsumer("localhost:9092", "test-group")
    topics = ["test-topic"]
    consumer.subscribe(topics)
    mock_kafka_consumer.return_value.subscribe.assert_called_once_with(topics)


@patch("tracking_service.consumer.Consumer")
def test_tracking_consumer_process_valid_message(
    mock_kafka_consumer, sample_order_data
):
    """Test processing of valid messages."""
    # Create a mock message
    mock_message = MagicMock(spec=Message)
    mock_message.error.return_value = None
    mock_message.value.return_value = json.dumps(sample_order_data).encode()

    # Setup the consumer
    mock_kafka_consumer.return_value.poll.side_effect = [
        mock_message,
        KeyboardInterrupt,  # To break the processing loop
    ]

    consumer = TrackingConsumer("localhost:9092", "test-group")
    mock_handler = MagicMock()

    # Process messages
    consumer.process_messages(mock_handler)

    # Verify handler was called with correct data
    assert mock_handler.call_count == 1
    called_event = mock_handler.call_args[0][0]
    assert isinstance(called_event, TrackingEvent)
    assert called_event.order_id == sample_order_data["order_id"]
    assert called_event.customer_id == sample_order_data["customer_id"]
    assert len(called_event.items) == len(sample_order_data["items"])


def test_tracking_producer_init():
    """Test TrackingProducer initialization."""
    producer = TrackingProducer(
        bootstrap_servers="localhost:9092", client_id="test-client"
    )
    assert producer.producer is not None


@patch("tracking_service.producer.Producer")
def test_tracking_producer_send_update(mock_kafka_producer, sample_tracking_event):
    """Test sending tracking updates."""
    producer = TrackingProducer("localhost:9092", "test-client")

    # Send an update
    producer.send_tracking_update("test-topic", sample_tracking_event)

    # Verify the message was produced
    mock_kafka_producer.return_value.produce.assert_called_once()
    call_args = mock_kafka_producer.return_value.produce.call_args
    assert call_args[1]["topic"] == "test-topic"
    assert call_args[1]["key"] == sample_tracking_event.order_id

    # Verify the message value can be decoded and contains correct data
    value = json.loads(call_args[1]["value"].decode("utf-8"))
    assert value["order_id"] == sample_tracking_event.order_id
    assert value["customer_id"] == sample_tracking_event.customer_id
    assert len(value["items"]) == len(sample_tracking_event.items)
