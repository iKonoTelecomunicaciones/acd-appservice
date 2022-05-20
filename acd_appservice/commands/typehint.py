from __future__ import annotations

from typing import List

from mautrix.appservice import IntentAPI
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from acd_appservice.agent_manager import AgentManager


class CommandEvent:
    agent_manager: AgentManager
    log: TraceLogger
    intent: IntentAPI
    sender: UserID
    room_id: RoomID
    text: str
    command_prefix: str
    cmd: str
    args: List[str] | None = None

    def __init__(
        self,
        cmd,
        agent_manager: AgentManager,
        sender: UserID,
        room_id: RoomID,
        text: str,
        intent: IntentAPI,
        args: List[str] = None,
    ):
        self.cmd = cmd
        self.log = self.log.getChild(self.cmd)
        self.agent_manager = agent_manager
        self.config = agent_manager.config
        self.command_prefix = self.config["bridge.command_prefix"]
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
        if not text:
            return

        try:
            await self.intent.send_notice(room_id=self.room_id, text=text, html=text)
        except Exception as e:
            self.log.exception(e)
