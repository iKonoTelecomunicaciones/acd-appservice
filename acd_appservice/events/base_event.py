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
from .event_types import ACDEventTypes, ACDMemberEvents, ACDMembershipEvents, ACDPortalEvents
from .nats_client import NatsClient

log: TraceLogger = logging.getLogger("report.event")


@dataclass
class BaseEvent(SerializableAttrs):
    event_type: ACDEventTypes = ib(default=None)
    event: ACDPortalEvents | ACDMemberEvents | ACDMembershipEvents = ib(default=None)
    timestamp: float = ib(default=datetime.utcnow().timestamp())
    sender: UserID = ib(factory=UserID)

    def send(self):
        asyncio.create_task(self.http_send())

    async def http_send(self):
        jetstream: JetStreamContext = None

        file = open("/data/room_events.txt", "a")
        file.write(f"{json.dumps(self.serialize())}\n\n")
        if self.event_type == ACDEventTypes.PORTAL and self.state == PortalState.RESOLVED:
            file.write(f"################# ------- New conversation ------- #################\n")
        file.close()
        log.info(f"Sending event {self.serialize()}")

        _, jetstream = await NatsClient.get_connection()
        if jetstream:
            try:
                await jetstream.publish(
                    subject=f"events.{self.event_type}",
                    payload=json.dumps(self.serialize()).encode(),
                )
            except Exception as e:
                log.error(f"Error publishing event to NATS: {e}")
