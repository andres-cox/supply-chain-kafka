==============
Tracking Service
==============

A microservice for tracking order status throughout the supply chain system.

Features
--------

* Consumes order events from the order service
* Tracks order status and updates
* Produces tracking events for other services
* Supports real-time status updates

Installation
-----------

Requirements:

* Python 3.10+
* Poetry for dependency management
* Kafka cluster

Install dependencies::

    poetry install

Configuration
------------

The service can be configured using environment variables:

* ``KAFKA_BOOTSTRAP_SERVERS``: Kafka broker addresses (default: localhost:9092)
* ``KAFKA_CONSUMER_GROUP``: Consumer group ID (default: tracking-service-group)
* ``KAFKA_CLIENT_ID``: Producer client ID (default: tracking-service)
* ``KAFKA_INPUT_TOPIC``: Topic to consume orders from (default: orders)
* ``KAFKA_OUTPUT_TOPIC``: Topic to produce tracking updates to (default: tracking-updates)

Running the Service
-----------------

Start the service::

    poetry run python -m tracking_service.main

Running Tests
-----------

Run the test suite::

    poetry run pytest

Development
----------

The service follows these coding standards:

* Google-style docstrings
* Type hints with mypy validation
* Ruff for linting and formatting
* Pytest for testing

Contributing
-----------

1. Create a feature branch
2. Make your changes
3. Run tests and linting
4. Submit a pull request