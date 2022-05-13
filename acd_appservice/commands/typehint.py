from __future__ import annotations

from typing import TYPE_CHECKING, List

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

if TYPE_CHECKING:
    from ..__main__ import ACDAppService

from mautrix.appservice import IntentAPI


class CommandEvent:
    acd_appservice: "ACDAppService"
    log: TraceLogger
    intent: IntentAPI
    sender: UserID
    room_id: RoomID
    text: str
    args: List[str] | None = None

    def __init__(
        self,
        acd_appservice: ACDAppService,
        sender: UserID,
        room_id: RoomID,
        text: str,
        intent: IntentAPI,
        args: List[str] = None,
    ):
        self.acd_appservice = acd_appservice
        self.log = acd_appservice.log

        self.sender = sender
        self.room_id = room_id
        self.text = text
        self.args = args
        self.intent = intent

    async def reply(self, text: str) -> None:
        """It sends a message to the room that the event was received from

        Parameters
        ----------
        text : str
            The text to send.

        """
        try:
            await self.intent.send_notice(room_id=self.room_id, text=text, html=text)
        except Exception as e:
            self.log.exception(e)
