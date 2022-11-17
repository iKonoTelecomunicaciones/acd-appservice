from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List

from attr import dataclass
from markdown import markdown
from mautrix.appservice import IntentAPI
from mautrix.types import Format, MessageType, RoomID, TextMessageEventContent
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..user import User

if TYPE_CHECKING:
    from ..__main__ import ACDAppService


class BaseCommandEvent:
    log: TraceLogger = logging.getLogger("acd.cmd")

    def __init__(
        self,
        sender: User,
        config: Config,
        command: str,
        is_management: bool,
        args: ArgParser = None,
        intent: IntentAPI = None,
        room_id: RoomID = None,
        text: str = None,
        args_list: List[str] = None,
    ):
        self.command = command
        self.log = self.log.getChild(self.command)
        self.intent = intent
        self.config = config
        self.command_prefix = config["bridge.command_prefix"]
        self.sender = sender
        self.room_id = room_id
        self.is_management = is_management
        self.text = text
        self.args_list = args_list
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


class CommandEvent(BaseCommandEvent):
    program: "ACDAppService"
    sender: "User"


@dataclass
class CommandArg:
    name: str
    help_text: str
    example: str
    default: Any = None
    is_required: bool = False

    @property
    def _name(self) -> str:
        return f"<_{self.name}_>" if self.is_required else f"[_{self.name}_]"

    @property
    def detail(self) -> str:
        return (
            f"**{self.name}**: {self.help_text}\n\n"
            f"\t**is_required**: {self.is_required}\n\n"
            f"\t**example**: {self.example}\n\n"
        )


class ArgParser:
    pass
