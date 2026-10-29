"""Contract for the live stream. Services never import Kafka: infrastructure/kafka_stream_source.py implements this,
and api/dependencies.py chooses the implementation."""
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal, Protocol

StreamKind = Literal["telemetry", "reefer"]


class StreamSource(Protocol):
    def messages(self, since: datetime) -> AsyncIterator[tuple[StreamKind, dict]]:
        """Every message produced at or after `since`, then new ones as they arrive (never ends), as (kind, row).
        row is the message JSON as a dict (catalog 3.14 / 3.15 columns + the silver flags)."""
        ...
