import logging
from datetime import datetime
from typing import Optional

from aiohttp import ClientSession
from attr import dataclass, ib
from mautrix.api import HTTPAPI
from mautrix.types import SerializableAttrs, SerializableEnum, UserID
from mautrix.util.logging import TraceLogger

from ...portal import PortalState

log: TraceLogger = logging.getLogger("acd.events")


class ACDEventsType(SerializableEnum):
    PORTAL = "PORTAL"


class ACDPortalEvents(SerializableEnum):
    Create = "Create"
    UIC = "UIC"
    EnterQueue = "EnterQueue"
    Connect = "Connect"
    AgentMessage = "AgentMessage"
    CustomerMessage = "CustomerMessage"
    Resolve = "Resolve"
    Transfer = "Transfer"


@dataclass
class BaseEvent(SerializableAttrs):
    type: ACDEventsType = ib(default=None)
    event: ACDPortalEvents = ib(default=None)
    timestamp: float = ib(default=datetime.utcnow().timestamp())
    state: PortalState = ib(default=None)
    prev_state: Optional[PortalState] = ib(default=None)
    sender: UserID = ib(factory=UserID)

    def fill(self) -> "BaseEvent":
        return self

    async def send(self):
        await self.http_send()

    async def http_send(self):
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
