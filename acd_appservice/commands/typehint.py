from __future__ import annotations

import logging
from typing import List

from markdown import markdown
from mautrix.appservice import IntentAPI
from mautrix.types import Format, MessageType, RoomID, TextMessageEventContent, UserID
from mautrix.util.logging import TraceLogger

from ..config import Config


class CommandEvent:
    log: TraceLogger = logging.getLogger("acd.cmd")
    sender: UserID
    room_id: RoomID | None
    text: str | None = None
    command_prefix: str
    cmd: str
    args: List[str] | None = []

    def __init__(
        self,
        cmd: str,
        sender: UserID,
        room_id: RoomID,
        config: Config,
        intent: IntentAPI,
        text: str = None,
        args: List[str] = None,
    ):
        self.cmd = cmd
        self.log = self.log.getChild(self.cmd)
        self.config = config
        self.intent = intent
        self.command_prefix = self.config["bridge.command_prefix"]
        self.sender = sender
        self.room_id = room_id
        self.text = text
        self.args = args

    async def reply(self, text: str) -> None:
        """It sends a message to the room that the event was received from

        Parameters
        ----------
        text : str
            The text to send.

        """
        if not text or not self.room_id:
            return

        try:
            # Sending a message to the room that the event was received from.
            html = markdown(text)
            content = TextMessageEventContent(
                msgtype=MessageType.NOTICE, body=text, format=Format.HTML, formatted_body=html
            )

            await self.intent.send_message(
                room_id=self.room_id,
                content=content,
            )
        except Exception as e:
            self.log.exception(e)
