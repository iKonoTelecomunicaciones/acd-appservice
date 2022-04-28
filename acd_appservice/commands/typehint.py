from __future__ import annotations

from typing import TYPE_CHECKING, List

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

if TYPE_CHECKING:
    from ..__main__ import ACDAppService


class CommandEvent:
    acd_appservice: "ACDAppService"
    log: TraceLogger

    sender_user_id: UserID
    room_id: RoomID
    text: str
    args: List[str] | None = None

    def __init__(
        self,
        acd_appservice: ACDAppService,
        sender_user_id: UserID,
        room_id: RoomID,
        text: str,
        args: List[str] = None,
    ):
        self.acd_appservice = acd_appservice
        self.log = acd_appservice.log

        self.sender_user_id = sender_user_id
        self.room_id = room_id
        self.text = text
        self.args = args
