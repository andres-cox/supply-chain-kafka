"""Tests for the notification service."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from confluent_kafka import Consumer
from fastapi.testclient import TestClient

from notification_service.consumer import NotificationConsumer
from notification_service.handler import EmailNotificationChannel, NotificationHandler, SMSNotificationChannel
from notification_service.schemas import Notification, NotificationPreferences, OrderStatus
from notification_service.server import app, state


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_kafka_consumer(mocker):
    """Mock the Kafka consumer."""
    consumer_mock = mocker.MagicMock(spec=Consumer)
    mocker.patch("notification_service.consumer.Consumer", return_value=consumer_mock)
    return consumer_mock


@pytest.fixture
def mock_smtp(mocker):
    """Mock SMTP server."""
    smtp_mock = mocker.MagicMock()
    mocker.patch("smtplib.SMTP", return_value=smtp_mock)
    return smtp_mock


@pytest.fixture
def mock_requests(mocker):
    """Mock requests for SMS API."""
    return mocker.patch("notification_service.handler.requests")


@pytest.fixture
def notification_handler():
    """Fixture for NotificationHandler."""
    return NotificationHandler()


@pytest.fixture
def notification_consumer(mock_kafka_consumer, notification_handler):
    """Fixture for NotificationConsumer."""
    return NotificationConsumer(consumer=mock_kafka_consumer, handler=notification_handler)


def test_health_check(test_client):
    """Test the health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_notification_preferences():
    """Test notification preferences validation and defaults."""
    # Test with minimal required fields
    prefs = NotificationPreferences(customer_id="cust-12345")
    assert prefs.channels == ["email"]  # Default channel
    assert "fraud_alert" in prefs.types  # Default notification types

    # Test with custom settings
    prefs = NotificationPreferences(
        customer_id="cust-12345",
        email="test@example.com",
        sms="+1234567890",
        channels=["sms"],
        types=["delivery_update"],
    )
    assert prefs.channels == ["sms"]
    assert prefs.types == ["delivery_update"]


def test_email_notification_channel(mock_smtp):
    """Test email notification channel."""
    channel = EmailNotificationChannel()

    notification = Notification(
        customer_id="cust-12345", type="fraud_alert", subject="Test Alert", message="Test message"
    )

    preferences = NotificationPreferences(customer_id="cust-12345", email="test@example.com")

    # Test successful email sending
    result = channel.send(notification, preferences)
    assert result is True
    mock_smtp.return_value.__enter__.return_value.send_message.assert_called_once()

    # Test with missing email
    preferences.email = None
    result = channel.send(notification, preferences)
    assert result is False


def test_sms_notification_channel(mock_requests):
    """Test SMS notification channel."""
    channel = SMSNotificationChannel()

    notification = Notification(
        customer_id="cust-12345", type="fraud_alert", subject="Test Alert", message="Test message"
    )

    preferences = NotificationPreferences(customer_id="cust-12345", sms="+1234567890")

    # Test successful SMS sending
    mock_requests.post.return_value.status_code = 200
    result = channel.send(notification, preferences)
    assert result is True
    mock_requests.post.assert_called_once()

    # Test with missing phone number
    preferences.sms = None
    result = channel.send(notification, preferences)
    assert result is False


def test_notification_handler():
    """Test notification handler with multiple channels."""
    handler = NotificationHandler()

    # Mock both channels
    handler.channels["email"] = MagicMock()
    handler.channels["sms"] = MagicMock()
    handler.channels["email"].send.return_value = True
    handler.channels["sms"].send.return_value = True

    notification = Notification(
        customer_id="cust-12345", type="fraud_alert", subject="Test Alert", message="Test message"
    )

    preferences = NotificationPreferences(
        customer_id="cust-12345", email="test@example.com", sms="+1234567890", channels=["email", "sms"]
    )

    # Test sending through multiple channels
    handler.send_notification(notification, preferences)
    handler.channels["email"].send.assert_called_once()
    handler.channels["sms"].send.assert_called_once()


def test_consumer_message_processing(mock_kafka_consumer):
    """Test consumer message processing."""
    consumer = NotificationConsumer(bootstrap_servers="dummy", group_id="test-group")

    # Set up test preferences
    preferences = NotificationPreferences(customer_id="cust-12345", email="test@example.com")
    consumer.set_preferences(preferences)

    # Verify preferences storage
    stored_prefs = consumer.get_preferences("cust-12345")
    assert stored_prefs == preferences

    # Test notification handling
    notification = Notification(
        customer_id="cust-12345", type="fraud_alert", subject="Test Alert", message="Test message"
    )

    # Mock notification handler
    handler_mock = MagicMock()
    consumer.process_messages(handler_mock)

    # Verify consumer subscription
    mock_kafka_consumer.subscribe.assert_called_once()


def test_notification_endpoints(test_client):
    """Test notification API endpoints."""
    # Test setting preferences
    preferences_data = {
        "customer_id": "cust-12345",
        "email": "test@example.com",
        "sms": "+1234567890",
        "channels": ["email", "sms"],
        "types": ["fraud_alert", "delivery_update"],
    }

    response = test_client.post("/preferences", json=preferences_data)
    assert response.status_code == 200
    assert response.json()["customer_id"] == preferences_data["customer_id"]

    # Test getting preferences
    response = test_client.get("/preferences/cust-12345")
    assert response.status_code == 200
    assert response.json()["email"] == preferences_data["email"]

    # Test getting non-existent preferences
    response = test_client.get("/preferences/non-existent")
    assert response.status_code == 404

    # Create test notification
    notification = Notification(
        customer_id="cust-12345", type="fraud_alert", subject="Test Alert", message="Test message"
    )
    state.store_notification(notification)

    # Test getting notifications
    response = test_client.get("/notifications")
    assert response.status_code == 200
    notifications = response.json()
    assert len(notifications) > 0
    assert notifications[0]["customer_id"] == "cust-12345"

    # Test getting specific notification
    response = test_client.get(f"/notifications/{notification.notification_id}")
    assert response.status_code == 200
    assert response.json()["notification_id"] == notification.notification_id

    # Test filtering notifications
    response = test_client.get("/notifications", params={"customer_id": "cust-12345"})
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = test_client.get("/notifications", params={"notification_type": "fraud_alert"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_notification_for_order_status():
    """Test creating notification for order status."""
    handler = NotificationHandler()
    order_status = OrderStatus(
        order_id="123", status="CONFIRMED", customer_id="456", timestamp="2025-04-30T10:00:00Z"
    )

    notification = handler.create_notification(order_status)
    assert isinstance(notification, Notification)
    assert notification.order_id == "123"
    assert notification.customer_id == "456"
    assert "confirmed" in notification.message.lower()


@pytest.mark.asyncio
async def test_consumer_message_processing_async(notification_consumer, mock_kafka_consumer):
    """Test async consumer message processing."""
    # Mock message
    message = Mock()
    message.value = {
        "order_id": "123",
        "status": "CONFIRMED",
        "customer_id": "456",
        "timestamp": "2025-04-30T10:00:00Z",
    }

    # Test processing
    with patch("notification_service.consumer.NotificationConsumer.process_message") as mock_process:
        await notification_consumer.consume()
        mock_process.assert_called_once()


def test_notification_handler_different_statuses():
    """Test notification handler with different order statuses."""
    handler = NotificationHandler()

    # Test different order statuses
    statuses = ["CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED"]

    for status in statuses:
        order_status = OrderStatus(
            order_id="123", status=status, customer_id="456", timestamp="2025-04-30T10:00:00Z"
        )

        notification = handler.create_notification(order_status)
        assert isinstance(notification, Notification)
        assert notification.order_id == "123"
        assert status.lower() in notification.message.lower()


@pytest.mark.asyncio
async def test_notification_sending(notification_handler):
    """Test sending notification."""
    notification = Notification(
        notification_id="789",
        customer_id="456",
        order_id="123",
        message="Your order has been confirmed",
        timestamp="2025-04-30T10:00:00Z",
    )

    with patch("notification_service.handler.NotificationHandler.send_notification") as mock_send:
        await notification_handler.send_notification(notification)
        mock_send.assert_called_once_with(notification)
