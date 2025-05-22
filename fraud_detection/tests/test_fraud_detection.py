"""Tests for the fraud detection service."""

import json
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from confluent_kafka import Producer, Consumer
from unittest.mock import Mock, patch

from fraud_detection import __version__
from fraud_detection.schemas import FraudAlert, LocationData, Order, FraudCheckResult
from fraud_detection.server import app, state
from fraud_detection.consumer import FraudDetectionConsumer
from fraud_detection.producer import FraudAlertProducer, FraudDetectionProducer


def test_version():
    assert __version__ == "0.1.0"


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_kafka_producer(mocker):
    """Mock the Kafka producer."""
    producer_mock = mocker.MagicMock(spec=Producer)
    mocker.patch("fraud_detection.producer.Producer", return_value=producer_mock)
    return producer_mock


@pytest.fixture
def mock_kafka_consumer(mocker):
    """Mock the Kafka consumer."""
    consumer_mock = mocker.MagicMock(spec=Consumer)
    mocker.patch("fraud_detection.consumer.Consumer", return_value=consumer_mock)
    return consumer_mock


@pytest.fixture
def mock_kafka_consumer():
    return Mock()


@pytest.fixture
def mock_kafka_producer():
    return Mock()


@pytest.fixture
def fraud_consumer(mock_kafka_consumer):
    return FraudDetectionConsumer(consumer=mock_kafka_consumer)


@pytest.fixture
def fraud_producer(mock_kafka_producer):
    return FraudDetectionProducer(producer=mock_kafka_producer)


@pytest.fixture
def fraud_detection_consumer(mock_kafka_consumer, mock_kafka_producer):
    return FraudDetectionConsumer(consumer=mock_kafka_consumer, producer=mock_kafka_producer)


def test_health_check(test_client):
    """Test the health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_process_rapid_movement(mock_kafka_producer):
    """Test detection of suspicious rapid movement."""
    # Create two locations with suspicious speed between them
    loc1 = LocationData(
        latitude=40.7128, longitude=-74.0060, timestamp=datetime.utcnow() - timedelta(minutes=5)
    )
    loc2 = LocationData(
        latitude=34.0522,
        longitude=-118.2437,  # LA coordinates - unrealistic speed from NYC
        timestamp=datetime.utcnow(),
    )

    # Create test order data
    order_data = {"order_id": "test-order-123", "customer_id": "test-customer-456", "status": "in_transit"}

    # Initialize consumer with mocked Kafka
    consumer = FraudDetectionConsumer(bootstrap_servers="dummy", group_id="test-group")

    # Process order and locations
    consumer._process_order(order_data)
    consumer._check_rapid_movement(
        order_id=order_data["order_id"],
        prev_location=loc1,
        curr_location=loc2,
        location_data={"customer_id": order_data["customer_id"]},
        alert_handler=lambda x: None,
    )

    # Verify alert was generated
    alerts = state.list_alerts(order_data["order_id"])
    assert len(alerts) > 0
    alert = alerts[0]
    assert alert.alert_type == "rapid_location_change"
    assert alert.order_id == order_data["order_id"]
    assert alert.confidence_score > 0.8  # High confidence due to unrealistic speed


def test_fraud_alert_producer(mock_kafka_producer):
    """Test the fraud alert producer."""
    producer = FraudAlertProducer(bootstrap_servers="dummy", client_id="test-producer")

    # Create test alert
    alert = FraudAlert(
        order_id="test-order-123",
        customer_id="test-customer-456",
        alert_type="rapid_location_change",
        confidence_score=0.9,
        details="Test alert",
        location_data=LocationData(latitude=40.7128, longitude=-74.0060),
    )

    # Send alert
    producer.send_fraud_alert("test-topic", alert)

    # Verify producer was called correctly
    mock_kafka_producer.produce.assert_called_once()
    call_args = mock_kafka_producer.produce.call_args[1]
    assert call_args["topic"] == "test-topic"
    assert call_args["key"] == alert.order_id

    # Verify message value
    produced_value = json.loads(call_args["value"].decode("utf-8"))
    assert produced_value["order_id"] == alert.order_id
    assert produced_value["alert_type"] == alert.alert_type


def test_get_alerts_endpoint(test_client):
    """Test the get alerts endpoint."""
    # Create test alert
    alert = FraudAlert(
        order_id="test-order-123",
        customer_id="test-customer-456",
        alert_type="rapid_location_change",
        confidence_score=0.9,
        details="Test alert",
        location_data=LocationData(latitude=40.7128, longitude=-74.0060),
    )
    state.store_alert(alert)

    # Test getting all alerts
    response = test_client.get("/alerts")
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) > 0
    assert alerts[0]["order_id"] == alert.order_id

    # Test getting specific alert
    response = test_client.get(f"/alerts/{alert.alert_id}")
    assert response.status_code == 200
    assert response.json()["alert_id"] == alert.alert_id

    # Test filtering by order ID
    response = test_client.get("/alerts", params={"order_id": alert.order_id})
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 1
    assert alerts[0]["order_id"] == alert.order_id


def test_calculate_distance():
    """Test the distance calculation function."""
    consumer = FraudDetectionConsumer(bootstrap_servers="dummy", group_id="test-group")

    # Test NYC to LA distance (approximately 3936 km)
    distance = consumer._calculate_distance(
        40.7128,
        -74.0060,  # NYC
        34.0522,
        -118.2437,  # LA
    )

    assert 3900 <= distance <= 4000  # Allow for some floating point variance


def test_fraud_detection_valid_order(fraud_consumer, fraud_producer):
    # Test data
    valid_order = Order(
        order_id="123",
        customer_id="456",
        total_amount=100.0,
        items=[{"item_id": "789", "quantity": 1, "price": 100.0}],
    )

    # Test fraud detection logic
    result = fraud_consumer.check_fraud(valid_order)
    assert isinstance(result, FraudCheckResult)
    assert result.is_fraudulent is False
    assert result.order_id == "123"
    assert result.reason is None


def test_fraud_detection_suspicious_order(fraud_consumer, fraud_producer):
    # Test data for suspicious order (high amount)
    suspicious_order = Order(
        order_id="123",
        customer_id="456",
        total_amount=10000.0,  # Suspicious amount
        items=[{"item_id": "789", "quantity": 1, "price": 10000.0}],
    )

    # Test fraud detection logic
    result = fraud_consumer.check_fraud(suspicious_order)
    assert isinstance(result, FraudCheckResult)
    assert result.is_fraudulent is True
    assert result.order_id == "123"
    assert "suspicious amount" in result.reason.lower()


@pytest.mark.asyncio
async def test_consumer_message_processing(fraud_consumer, mock_kafka_consumer):
    # Mock message
    message = Mock()
    message.value = {
        "order_id": "123",
        "customer_id": "456",
        "total_amount": 100.0,
        "items": [{"item_id": "789", "quantity": 1, "price": 100.0}],
    }

    # Test processing
    with patch("fraud_detection.consumer.FraudDetectionConsumer.process_message") as mock_process:
        await fraud_consumer.consume()
        mock_process.assert_called_once()


@pytest.mark.asyncio
async def test_producer_send_result(fraud_producer, mock_kafka_producer):
    # Test data
    result = FraudCheckResult(order_id="123", is_fraudulent=False, reason=None)

    # Test sending result
    await fraud_producer.send_result(result)
    mock_kafka_producer.send.assert_called_once()


def test_check_order_fraud_normal_case():
    consumer = FraudDetectionConsumer(consumer=Mock(), producer=Mock())
    order = Order(
        order_id="123",
        customer_id="456",
        total_amount=100.00,
        items=[{"item_id": "789", "quantity": 1, "price": 100.00}],
        timestamp=datetime.now().isoformat(),
    )

    result = consumer.check_fraud(order)
    assert isinstance(result, FraudCheckResult)
    assert result.order_id == "123"
    assert result.is_fraudulent is False


def test_check_order_fraud_suspicious_amount():
    consumer = FraudDetectionConsumer(consumer=Mock(), producer=Mock())
    order = Order(
        order_id="123",
        customer_id="456",
        total_amount=10000.00,  # Suspicious high amount
        items=[{"item_id": "789", "quantity": 1, "price": 10000.00}],
        timestamp=datetime.now().isoformat(),
    )

    result = consumer.check_fraud(order)
    assert isinstance(result, FraudCheckResult)
    assert result.order_id == "123"
    assert result.is_fraudulent is True
    assert "suspicious amount" in result.reason.lower()


@pytest.mark.asyncio
async def test_consumer_message_processing(fraud_detection_consumer, mock_kafka_consumer):
    # Mock message
    message = Mock()
    message.value = {
        "order_id": "123",
        "customer_id": "456",
        "total_amount": 100.00,
        "items": [{"item_id": "789", "quantity": 1, "price": 100.00}],
        "timestamp": datetime.now().isoformat(),
    }

    # Test processing
    with patch("fraud_detection.consumer.FraudDetectionConsumer.process_message") as mock_process:
        await fraud_detection_consumer.consume()
        mock_process.assert_called_once()


def test_multiple_orders_from_same_customer():
    consumer = FraudDetectionConsumer(consumer=Mock(), producer=Mock())

    # Create multiple orders for the same customer
    customer_id = "456"
    orders = []
    for i in range(5):
        order = Order(
            order_id=f"order_{i}",
            customer_id=customer_id,
            total_amount=100.00,
            items=[{"item_id": "789", "quantity": 1, "price": 100.00}],
            timestamp=datetime.now().isoformat(),
        )
        orders.append(order)

    # Process all orders
    results = [consumer.check_fraud(order) for order in orders]

    # The last order should be flagged as suspicious due to frequency
    assert results[-1].is_fraudulent is True
    assert "frequency" in results[-1].reason.lower()


@pytest.mark.asyncio
async def test_fraud_result_publishing(fraud_detection_consumer, mock_kafka_producer):
    result = FraudCheckResult(
        order_id="123",
        is_fraudulent=True,
        reason="Suspicious activity detected",
        timestamp=datetime.now().isoformat(),
    )

    with patch("fraud_detection.consumer.FraudDetectionConsumer.publish_result") as mock_publish:
        await fraud_detection_consumer.publish_result(result)
        mock_publish.assert_called_once_with(result)
