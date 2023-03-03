import logging
import time
from typing import ClassVar, Optional

from aiohttp import ClientSession
from attr import dataclass
from mautrix.api import HTTPAPI
from mautrix.types import SerializableAttrs, SerializableEnum, UserID
from mautrix.util.logging import TraceLogger

log: TraceLogger = logging.getLogger("report")


class ACDState(SerializableEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"


@dataclass(kw_only=True)
class Reporter(SerializableAttrs):

    default_source: ClassVar[str] = "state"
    acd_state: ACDState
    user_id: Optional[UserID] = None
    timestamp: Optional[int] = None
    source: Optional[str] = None

    def fill(self) -> "Reporter":
        self.timestamp = self.timestamp or int(time.time())
        self.source = self.source or self.default_source
        return self

    async def send(self):
        await self.http_send()

    async def http_send(self):
        log.info(f"Sending event {self.serialize()}")
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
