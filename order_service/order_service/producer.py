"""Kafka producer for publishing order events."""

from confluent_kafka import Producer

from .logger import logger
from .schemas import OrderSchema


class OrderProducer:
    """Kafka producer for publishing order events.

    This class handles the publishing of order events to Kafka topics using
    consistent partitioning to ensure ordered delivery of messages with the same key.

    Attributes:
        _producer: The underlying Kafka producer instance.
    """

    def __init__(self, bootstrap_servers: str):
        """Initialize the Kafka producer with the given bootstrap servers.

        Args:
            bootstrap_servers (str): Comma-separated list of Kafka broker addresses.
        """
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "message.timeout.ms": 5000,
                "partitioner": "consistent_random",  # Same key → same partition
            }
        )

    @property
    def producer(self):
        """Get the underlying Kafka producer instance.

        Returns:
            Producer: The Kafka producer instance.
        """
        return self._producer

    def _delivery_callback(self, err, msg):
        """Callback function for message delivery reports.

        Args:
            err: Error that occurred during message delivery, if any.
            msg: Message that was delivered or failed.
        """
        if err:
            logger.error(f"Message failed delivery: {err}", extra={"topic": msg.topic(), "key": msg.key()})
        else:
            logger.debug(
                f"Message delivered to {msg.topic()} [p:{msg.partition()}]",
                extra={"offset": msg.offset(), "latency": msg.latency()},
            )

    def publish_order(self, order: OrderSchema):
        """Publish an order to the Kafka topic.

        Args:
            order (OrderSchema): The order to publish.

        Raises:
            BufferError: If the producer's internal buffer is full.
        """
        try:
            self._producer.produce(
                topic="orders.created",
                key=order.order_id.encode("utf-8"),
                value=order.model_dump_json(exclude={"created_at"}),
                on_delivery=self._delivery_callback,
            )
            self.producer.poll(0)  # Trigger delivery callbacks
        except BufferError:
            logger.warning("Producer buffer full, flushing...")
            self.producer.flush()
            raise
