"""StreamSource on Kafka (aiokafka): reads both silver topics from `since`, then follows them live.
No consumer group: every backend instance reads every partition (each one keeps the whole fleet), and nothing is
committed (the history is read again from Kafka on every start)."""
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime

from aiokafka import AIOKafkaConsumer

from ..core.config import settings
from ..domain.stream_source import StreamKind

logger = logging.getLogger(__name__)


class KafkaStreamSource:
    def __init__(self):
        self._kinds: dict[str, StreamKind] = {
            settings.kafka_telemetry_topic: "telemetry",
            settings.kafka_reefer_topic: "reefer",
        }

    async def messages(self, since: datetime) -> AsyncIterator[tuple[StreamKind, dict]]:
        consumer = AIOKafkaConsumer(*self._kinds, bootstrap_servers=settings.kafka_bootstrap_servers, group_id=None, enable_auto_commit=False)
        await consumer.start()  # with no group, start() waits for both topics and takes all their partitions
        try:
            await _seek_to(consumer, since)
            async for message in consumer:
                try:
                    row = json.loads(message.value)
                except (TypeError, ValueError):  # malformed JSON (~0.02%, catalog A.6) or empty message
                    logger.warning("Skipped a message that is not JSON: %s[%s] offset %s", message.topic, message.partition, message.offset)
                    continue
                yield self._kinds[message.topic], row
        finally:
            await consumer.stop()


async def _seek_to(consumer: AIOKafkaConsumer, since: datetime) -> None:
    """Moves each partition to its first message produced at or after `since` (to the end when there is none)."""
    offsets = await consumer.offsets_for_times({partition: int(since.timestamp() * 1000) for partition in consumer.assignment()})
    for partition, found in offsets.items():
        if found is None:
            await consumer.seek_to_end(partition)
        else:
            consumer.seek(partition, found.offset)
