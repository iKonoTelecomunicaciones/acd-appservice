from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict

from markdown import markdown
from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import AppService, IntentAPI
from mautrix.types import Format, MessageType, RoomID, TextMessageEventContent, UserID
from mautrix.util.logging import TraceLogger

from .util import Util

if TYPE_CHECKING:
    from .__main__ import ACDAppService


class MatrixRoom:

    room_id: RoomID
    bridge: str
    log: TraceLogger = logging.getLogger("acd.room")
    az: AppService

    by_room_id: Dict[RoomID, "MatrixRoom"] = {}

    def __init__(self, room_id: RoomID, intent: IntentAPI = None):
        self.log = self.log.getChild(room_id)
        self.room_id = room_id
        self.main_intent = intent or self.az.intent

    @classmethod
    def init_cls(cls, bridge: "ACDAppService") -> None:
        cls.config = bridge.config
        cls.az = bridge.az

    async def post_init(self) -> None:
        """If the room is a control room, then the bridge is the bridge of the puppet.
        If the room is not a control room,
        then the bridge is the bridge of the puppet's control room

        Returns
        -------
            The room object

        """

        if not self.room_id:
            return

        if not self.room_id in self.by_room_id:
            self.by_room_id[self.room_id] = self

        if not self.main_intent:
            self.main_intent = self.az.intent

    async def invite_user(self, user_id: UserID):
        """Invite a user to the room

        Parameters
        ----------
        user_id : UserID
            The user ID of the user to invite.

        """
        await self.main_intent.invite_user(room_id=self.room_id, user_id=user_id)

    async def join_user(self, user_id: UserID):
        """It sends a POST request to the Synapse server,
        asking it to join the user with the given user_id to the room with the given room_id

        Parameters
        ----------
        user_id : UserID
            The user ID of the user to join the room.

        """
        await self.main_intent.api.request(
            method=Method.POST,
            path=SynapseAdminPath.v1.join[self.room_id],
            content={"user_id": user_id},
        )

    async def kick_user(self, user_id: UserID, reason: str | None = ""):
        """Kick a user from the room.

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to kick.
        reason : str | None
            The reason for the kick.

        """
        await self.main_intent.kick_user(room_id=self.room_id, user_id=user_id, reason=reason)

    async def leave_user(self, user_id: UserID, reason: str | None = ""):
        """leaves a user from the room

        Parameters
        ----------
        user_id : UserID
            The user ID of the user to kick.
        reason : str | None
            The reason for the user leaving the room.

        """
        data = {}
        if reason:
            data["reason"] = reason
        await self.main_intent.api.session.post(
            url=f"{self.main_intent.api.base_url}/_matrix/client/v3/rooms/{self.room_id}/leave",
            headers={"Authorization": f"Bearer {self.main_intent.api.token}"},
            json=data,
            params={"user_id": user_id},
        )

    async def leave(self, reason: str | None = None):
        """Leave the room, optionally with a reason.

        The first line is the function declaration.
        It's a function called `leave` that takes a single argument, `reason`

        Parameters
        ----------
        reason : str | None
            The reason for leaving the room.

        """
        await self.main_intent.leave_room(room_id=self.room_id, reason=reason)

    async def send_text(self, text: str | None = None, html: str | None = None):
        """It sends a text message to the room

        Parameters
        ----------
        text : str | None
            The text to send.
        html : str | None
            The HTML version of the message body.

        """
        await self.az.intent.send_text(
            room_id=self.room_id,
            text=text,
            html=html,
        )

    async def send_notice(self, text: str | None = None, html: str | None = None):
        """It sends a notice to the room

        Parameters
        ----------
        text : str | None
            The text to send.
        html : str | None
            The HTML version of the message.

        """
        await self.az.intent.send_notice(
            room_id=self.room_id,
            text=text,
            html=html,
        )

    async def send_message(self, content: TextMessageEventContent):
        """It sends a message to the room

        Parameters
        ----------
        content : TextMessageEventContent
            The content of the message.

        """
        await self.main_intent.send_message(
            room_id=self.room_id,
            content=content,
        )

    async def send_formatted_message(
        self,
        text: str,
    ) -> None:
        """It sends a message to a room, and the message is formatted using Markdown

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to send the message to.
        msg : str
            The message to send.

        """
        html = markdown(text)
        content = TextMessageEventContent(
            msgtype=MessageType.TEXT,
            body=text,
            format=Format.HTML,
            formatted_body=html,
        )

        # Remove markdown and html tags if bridge not support formatted messages
        if self.bridge and not self.config[f"bridges.{self.bridge}.format_messages"]:
            new_body = Util.md_to_text(content.get("body"))
            content["body"] = new_body if new_body else text

        await self.main_intent.send_message(
            room_id=self.room_id,
            content=content,
        )
