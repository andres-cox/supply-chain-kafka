import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Structured JSON logs for ELK/Grafana Loki"""
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "context": {
                "module": record.module,
                "line": record.lineno,
                **getattr(record, "extra", {})
            }
        }
        return json.dumps(log_record)

class KafkaFormatter(logging.Formatter):
    """Special formatter for Kafka-related logs (adds topic/partition info)"""
    def format(self, record):
        base = super().format(record)
        if hasattr(record, 'kafka_topic'):
            return f"{base} | topic={record.kafka_topic}"
        return base