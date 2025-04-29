"""Unit tests for the OrderProducer class."""

from unittest.mock import MagicMock, patch

from order_service.producer import OrderProducer


def test_producer_initialization():
    """Test that OrderProducer initializes with correct configuration.

    Verifies that the Kafka producer is created with the expected settings,
    including bootstrap servers, timeout, and partitioner configuration.
    """
    mock_producer_instance = MagicMock()
    mock_producer_class = MagicMock(return_value=mock_producer_instance)

    with patch("order_service.producer.Producer", new=mock_producer_class):
        producer = OrderProducer("dump:9092")

        # Verify Producer was called with correct config
        mock_producer_class.assert_called_once_with(
            {"bootstrap.servers": "dump:9092", "message.timeout.ms": 5000, "partitioner": "consistent_random"}
        )

        # Verify we got back our mock instance
        assert producer.producer == mock_producer_instance


def test_publish_order_success(test_producer, test_order):
    """Test successful order publication to Kafka.

    Args:
        test_producer: Fixture providing a configured OrderProducer instance
        test_order: Fixture providing a sample order for testing

    Verifies that:
        - The order is published to the correct topic
        - The message key is set to the order ID
        - The message value contains the serialized order
        - The delivery callback is properly set
        - Producer poll is called
    """
    # Mock the internal _producer instead
    with patch.object(test_producer, "_producer") as mock_producer:
        mock_producer.produce = MagicMock()
        test_producer.publish_order(test_order)

        mock_producer.produce.assert_called_once_with(
            topic="orders.created",
            key=test_order.order_id.encode("utf-8"),
            value=test_order.model_dump_json(exclude={"created_at"}),
            on_delivery=test_producer._delivery_callback,
        )
        mock_producer.poll.assert_called_once_with(0)
