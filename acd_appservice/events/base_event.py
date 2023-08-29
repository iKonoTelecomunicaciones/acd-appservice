from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from attr import dataclass, ib
from mautrix.types import SerializableAttrs, UserID
from mautrix.util.logging import TraceLogger
from nats.js.client import JetStreamContext

from ..db.portal import PortalState
from .event_types import (
    ACDConversationEvents,
    ACDEventTypes,
    ACDMemberEvents,
    ACDMembershipEvents,
    ACDRoomEvents,
)
from .nats_publisher import NatsPublisher

log: TraceLogger = logging.getLogger("report.event")


@dataclass
class BaseEvent(SerializableAttrs):
    event_type: ACDEventTypes = ib(default=None)
    event: ACDConversationEvents | ACDMemberEvents | ACDMembershipEvents | ACDRoomEvents = ib(
        default=None
    )
    timestamp: float = ib(default=datetime.utcnow().timestamp())
    sender: UserID = ib(factory=UserID)

    def send(self):
        asyncio.create_task(self.send_to_nats())

    async def send_to_nats(self):
        jetstream: JetStreamContext = None

        file = open("/data/room_events.txt", "a")
        file.write(f"{json.dumps(self.serialize())}\n\n")
        if self.event_type == ACDEventTypes.CONVERSATION and self.state == PortalState.RESOLVED:
            file.write(f"################# ------- New conversation ------- #################\n")
        file.close()
        log.error(f"Sending event {self.serialize()}")

        _, jetstream = await NatsPublisher.get_connection()
        if jetstream:
            try:
                subject = NatsPublisher.config["nats.subject"]
                await jetstream.publish(
                    subject=f"{subject}.{self.event_type}",
                    payload=json.dumps(self.serialize()).encode(),
                )
            except Exception as e:
                log.error(f"Error publishing event to NATS: {e}")
