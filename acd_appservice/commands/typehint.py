from __future__ import annotations

import logging
from typing import List

from markdown import markdown
from mautrix.types import Format, MessageType, RoomID, TextMessageEventContent, UserID
from mautrix.util.logging import TraceLogger

from acd_appservice.agent_manager import AgentManager


class CommandEvent:
    agent_manager: AgentManager
    log: TraceLogger = logging.getLogger("acd.cmd")
    sender: UserID
    room_id: RoomID | None
    text: str
    command_prefix: str
    cmd: str
    args: List[str] | None = None

    def __init__(
        self,
        cmd: str,
        agent_manager: AgentManager,
        sender: UserID,
        room_id: RoomID,
        text: str,
        args: List[str] = None,
    ):
        self.cmd = cmd
        self.log = self.log.getChild(self.cmd)
        self.agent_manager = agent_manager
        self.config = agent_manager.config
        self.intent = agent_manager.intent
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
