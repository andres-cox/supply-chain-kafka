"""Order Service Server."""

import os

from confluent_kafka.admin import AdminClient
from fastapi import APIRouter, FastAPI

from .logger import logger
from .producer import OrderProducer
from .schemas import OrderSchema

app = FastAPI()
router = APIRouter()

producer = OrderProducer(os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"))


@router.get("/health")
def health_check():
    """Check the health status of the service.

    Returns:
        dict: Contains Kafka connection status.
    """
    return {"kafka": _check_kafka_connection()}


@router.get("/health/ready")
def readiness_check():
    """Check if the service is ready to accept traffic.

    Returns:
        dict: Service readiness status and Kafka connection status.
    """
    kafka_ok = _check_kafka_connection()
    return {"status": "ready" if kafka_ok else "not_ready", "kafka": kafka_ok}


@router.post("/orders")
async def create_order(order: OrderSchema):
    """Create and publish a new order.

    Args:
        order (OrderSchema): The order data to be published.

    Returns:
        dict: Status of the order creation and order ID if successful.
    """
    logger.info(f"Received new order: {order}")
    try:
        producer.publish_order(order)
        logger.info(f"Order published successfully: {order.order_id}")
        return {"status": "success", "order_id": order.order_id}
    except Exception as e:
        logger.error(f"Failed to publish order {order.order_id}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _check_kafka_connection() -> bool:
    """Check if Kafka connection is available.

    Returns:
        bool: True if Kafka is accessible, False otherwise.
    """
    try:
        # logger.info("Checking Kafka connection...")
        admin = AdminClient({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS")})
        result = bool(admin.list_topics(timeout=5))
        # logger.info(f"Kafka connection status: {'connected' if result else 'no topics found'}")
        return result
    except Exception as e:
        logger.error(f"Kafka connection failed: {e}", exc_info=True)
        return False


app.include_router(router)
logger.info("API router mounted.")
