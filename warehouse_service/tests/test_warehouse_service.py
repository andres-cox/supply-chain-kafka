"""Tests for the Warehouse Service."""

from unittest.mock import Mock, patch
from http import HTTPStatus
from pydantic import ValidationError
import json

import pytest
from fastapi.testclient import TestClient

from warehouse_service.consumer import consume_orders, create_consumer
from warehouse_service.inventory import process_order
from warehouse_service.server import app


@pytest.fixture
def test_client():
    """Fixture for creating a test client."""
    return TestClient(app)


@pytest.fixture
def valid_order():
    """Fixture for a valid order."""
    return {
        "order_id": "order-123",
        "customer_id": "cust-456",
        "items": [
            {"sku": "ABC123", "quantity": 2, "price": 10.99},
            {"sku": "XYZ789", "quantity": 1, "price": 25.50},
        ],
        "created_at": "2025-04-24T10:00:00Z",
    }


def test_health_check(test_client):
    """Test the basic health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "healthy"}


@patch("warehouse_service.server.create_consumer")
@patch("warehouse_service.server.AdminClient")
def test_readiness_check_success(mock_admin_client, mock_create_consumer, test_client):
    """Test the readiness check when Kafka is available."""
    # Setup mock consumer
    mock_consumer = Mock()
    mock_consumer.config = {"bootstrap.servers": "kafka:9092"}
    mock_create_consumer.return_value = mock_consumer

    # Setup mock admin client
    mock_admin_instance = Mock()
    mock_admin_instance.list_topics.return_value = {"topics": ["test-topic"]}
    mock_admin_client.return_value = mock_admin_instance

    response = test_client.get("/health/ready")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ready", "kafka": "connected"}


def test_process_order_valid(valid_order):
    """Test processing a valid order."""
    process_order(valid_order)  # Should not raise any exceptions


def test_process_order_invalid():
    """Test processing an invalid order."""
    invalid_order = {"order_id": "123"}  # Missing required fields
    with pytest.raises(ValidationError):
        process_order(invalid_order)


@patch("warehouse_service.consumer.Consumer")
def test_create_consumer(mock_consumer):
    """Test Kafka consumer creation."""
    create_consumer()
    mock_consumer.assert_called_once_with(
        {
            "bootstrap.servers": "kafka:9092",
            "group.id": "warehouse-service",
            "auto.offset.reset": "earliest",
        }
    )


@patch("warehouse_service.consumer.Consumer")
def test_consume_orders_error_handling(mock_consumer):
    """Test error handling in the consumer."""
    mock_consumer_instance = Mock()
    mock_consumer.return_value = mock_consumer_instance

    # Create a message that will trigger a validation error
    invalid_order = {
        "invalid": "json",
        "order_id": None,  # This will cause a validation error
        "items": [],  # Empty items list will cause validation error
        "customer_id": "",  # Empty customer ID will cause validation error
        "created_at": "2025-04-24T10:00:00Z"
    }
    
    mock_message = Mock()
    mock_message.error.return_value = None
    mock_message.value.return_value = json.dumps(invalid_order).encode()
    
    # Set up the consumer to return our invalid message once, then None to stop the loop
    mock_consumer_instance.poll.side_effect = [mock_message, None]

    # Set up subscription
    mock_consumer_instance.subscribe = Mock()

    # The consumer should handle the validation error and continue
    consume_orders()

    # Verify the consumer subscribed to the correct topic
    mock_consumer_instance.subscribe.assert_called_once_with(["orders.created"])

    # Verify poll was called
    assert mock_consumer_instance.poll.call_count == 2
