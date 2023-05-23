import logging
from datetime import datetime
from typing import Optional

from aiohttp import ClientSession
from attr import dataclass, ib
from mautrix.api import HTTPAPI
from mautrix.types import SerializableAttrs, UserID
from mautrix.util.logging import TraceLogger

from ..db.portal import PortalState
from .models import ACDEventTypes, ACDPortalEvents

log: TraceLogger = logging.getLogger("report.event")


@dataclass
class BaseEvent(SerializableAttrs):
    event_type: ACDEventTypes = ib(default=None)
    event: ACDPortalEvents = ib(default=None)
    timestamp: float = ib(default=datetime.utcnow().timestamp())
    state: PortalState = ib(default=None)
    prev_state: Optional[PortalState] = ib(default=None)
    sender: UserID = ib(factory=UserID)

    async def send(self):
        await self.http_send()

    async def http_send(self):
        file = open("room_events.txt", "a")
        file.write(f"{self.serialize()}\n")
        file.close()
        log.error(f"Sending event {self.serialize()}")
        # headers = {"User-Agent": HTTPAPI.default_ua}
        # url = ""
        # try:
        #     async with ClientSession() as sess, sess.post(
        #         url, json=self.serialize(), headers=headers
        #     ) as resp:
        #         if not 200 <= resp.status < 300:
        #             text = await resp.text()
        #             text = text.replace("\n", "\\n")
        #             log.warning(
        #                 f"Unexpected status code {resp.status} "
        #                 f"sending bridge state update: {text}"
        #             )
        #             return False

        # except Exception as e:
        #     log.warning(f"Failed to send updated bridge state: {e}")
        #     return False
