import logging
import json
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "service": getattr(record, "service", "unknown"),
            "msg": record.getMessage(),
            "ts": self.formatTime(record),
        })


def setup_logging(service_name: str, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.LoggerAdapter(root, {"service": service_name})
    # attach service name to all records via a filter
    root.addFilter(lambda r: setattr(r, "service", service_name) or True)
