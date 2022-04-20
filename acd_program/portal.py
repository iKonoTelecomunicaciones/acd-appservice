from __future__ import annotations

import re
from typing import TYPE_CHECKING, AsyncGenerator, cast

from mautrix.appservice import AppService, IntentAPI
from mautrix.bridge import BasePortal, async_getter_lock
from mautrix.types import ContentURI, EventID, EventType, MessageEventContent, RoomID

from . import matrix as m
from . import puppet as p
from . import user as u
from .config import Config
from .db import Portal as DBPortal

if TYPE_CHECKING:
    from .__main__ import ACDAppService

StateBridge = EventType.find("m.bridge", EventType.Class.STATE)
StateHalfShotBridge = EventType.find("uk.half-shot.bridge", EventType.Class.STATE)

# This doesn't need to capture all valid URLs, it's enough to catch most of them.
# False negatives simply mean the link won't be linkified on Instagram,
# but false positives will cause the message to fail to send.
SIMPLE_URL_REGEX = re.compile(
    r"(?P<url>https?://[\da-z.-]+\.[a-z]{2,}(?:/[^\s]*)?)", flags=re.IGNORECASE
)


class Portal(DBPortal, BasePortal):
    by_mxid: dict[RoomID, Portal] = {}
    config: Config
    matrix: m.MatrixHandler
    az: AppService
    private_chat_portal_meta: bool

    _main_intent: IntentAPI | None

    def __init__(
        self,
        receiver: int,
        mxid: RoomID | None = None,
        name: str | None = None,
        avatar_url: ContentURI | None = None,
        name_set: bool = False,
        avatar_set: bool = False,
    ) -> None:
        super().__init__(
            receiver,
            mxid,
            name,
            avatar_url,
            name_set,
            avatar_set,
        )

        self._main_intent = None

    @property
    def main_intent(self) -> IntentAPI:
        if not self._main_intent:
            raise ValueError("Portal must be postinit()ed before main_intent can be used")
        return self._main_intent

    @classmethod
    def init_cls(cls, bridge: "ACDAppService") -> None:
        cls.config = bridge.config
        cls.matrix = bridge.matrix
        cls.az = bridge.az
        cls.loop = bridge.loop
        cls.bridge = bridge

    async def handle_matrix_message(
        self, sender: u.User, message: MessageEventContent, event_id: EventID
    ) -> None:
        try:
            await self._handle_matrix_message(sender, message, event_id)
        except Exception as e:
            self.log.exception(f"Fatal error handling Matrix event {event_id}: {e}")
            await self._send_bridge_error(
                sender,
                e,
                event_id,
                EventType.ROOM_MESSAGE,
                message_type=message.msgtype,
                status=self._status_from_exception(e),
                confirmed=True,
            )

    async def _handle_matrix_message(
        self, orig_sender: u.User, message: MessageEventContent, event_id: EventID
    ) -> None:
        pass

    async def delete(self) -> None:
        # await DBMessage.delete_all(self.mxid)
        self.by_mxid.pop(self.mxid, None)
        self.mxid = None
        self.encrypted = False
        await self.update()

    async def save(self) -> None:
        await self.update()

    @classmethod
    def all_with_room(cls) -> AsyncGenerator[Portal, None]:
        return cls._db_to_portals(super().all_with_room())

    @classmethod
    @async_getter_lock
    async def get_by_mxid(cls, mxid: RoomID) -> Portal | None:
        try:
            return cls.by_mxid[mxid]
        except KeyError:
            pass

        portal = cast(cls, await super().get_by_mxid(mxid))
        if portal is not None:
            await portal.postinit()
            return portal

        return None
