"""FastAPI entry point for the Warehouse Service."""

import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from confluent_kafka.admin import AdminClient
from .consumer import consume_orders, create_consumer
from .logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    consumer_thread = threading.Thread(target=consume_orders, daemon=True)
    consumer_thread.start()
    yield
    # Shutdown
    # Add any cleanup code here if needed


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness_check():
    """Readiness check that verifies Kafka connection."""
    try:
        # Test Kafka connection using the configuration directly
        admin = AdminClient({"bootstrap.servers": "kafka:9092"})
        cluster_metadata = admin.list_topics(timeout=10)
        if cluster_metadata is not None:
            return {"status": "ready", "kafka": "connected"}
    except Exception as e:
        logger.error(f"Kafka connection failed: {e}")
        return {"status": "not ready", "kafka": "disconnected"}
