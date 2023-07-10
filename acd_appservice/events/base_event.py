from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from aiohttp import ClientSession
from attr import dataclass, ib
from mautrix.api import HTTPAPI
from mautrix.types import SerializableAttrs, UserID
from mautrix.util.logging import TraceLogger

from ..db.portal import PortalState
from .event_types import ACDEventTypes, ACDMemberEvents, ACDMembershipEvents, ACDPortalEvents

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
        file = open("/data/room_events.txt", "a")
        file.write(f"{json.dumps(self.serialize())}\n\n")
        if self.event == ACDEventTypes.PORTAL and self.state == PortalState.RESOLVED:
            file.write(f"################# ------- New conversation ------- #################\n")
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
