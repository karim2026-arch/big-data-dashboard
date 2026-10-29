from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ...services.stream_service import StreamService
from ..dependencies import get_stream_service

router = APIRouter(tags=["stream"])


@router.get("/stream", response_class=EventSourceResponse)
async def stream(service: Annotated[StreamService, Depends(get_stream_service)]) -> AsyncIterable[ServerSentEvent]:
    """Live fleet over Server-Sent Events: events telemetry (list of rows), reefer (list of rows), alert (one AlertRow)
    and kpis (LiveKpis). A new viewer first gets a snapshot of everything, then only changes.
    See app/services/stream_service.py and dashboard/src/data/contract.js."""
    async for event, data in service.events():
        yield ServerSentEvent(event=event, data=data)
