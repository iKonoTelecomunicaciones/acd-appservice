from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from mautrix.appservice import IntentAPI
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from acd_appservice import matrix_handler as mh


class CommandEvent:
    matrix: mh.MatrixHandler
    log: TraceLogger  = logging.getLogger("acd.command")
    intent: IntentAPI
    sender: UserID
    room_id: RoomID
    text: str
    command_prefix: str
    cmd: str
    args: List[str] | None = None

    def __init__(
        self,
        matrix: mh.MatrixHandler,
        cmd,
        sender: UserID,
        room_id: RoomID,
        text: str,
        intent: IntentAPI,
        args: List[str] = None,
    ):
        self.matrix = matrix
        self.command_prefix = self.matrix.config["bridge.command_prefix"]
        self.cmd = cmd
        self.log = self.log.getChild(self.cmd)
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
