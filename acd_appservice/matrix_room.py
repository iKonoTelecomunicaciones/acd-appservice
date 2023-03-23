from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List

from markdown import markdown
from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import AppService, IntentAPI
from mautrix.types import Format, MessageType, RoomID, TextMessageEventContent, UserID
from mautrix.util.logging import TraceLogger

from .user import User
from .util import Util

if TYPE_CHECKING:
    from .__main__ import ACDAppService


class MatrixRoom:
    room_id: RoomID
    bridge: str
    log: TraceLogger = logging.getLogger("acd.matrix_room")
    az: AppService

    by_room_id: Dict[RoomID, "MatrixRoom"] = {}
    creator: UserID = None
    main_intent: IntentAPI = None

    def __init__(self, room_id: RoomID):
        self.log = self.log.getChild(room_id)
        self.room_id = room_id

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

        await self.set_creator()

    async def set_creator(self) -> None:
        """It sets the creator of the channel"""

        info = await self.get_info()

        if not info:
            return

        self.creator = info.get("creator")

    async def get_room_name(self) -> str:
        """It returns the name of the room

        Returns
        -------
            The name of the room.

        """

        info = await self.get_info()

        if not info:
            return

        return info.get("name")

    async def get_room_topic(self) -> str:
        """It returns the topic of the room

        Returns
        -------
            The topic of the room.

        """

        info = await self.get_info()

        if not info:
            return

        return info.get("topic")

    async def get_joined_users(self) -> List[User] | None:
        """get a list of all users in the room

        Returns
        -------
            A list of User objects.

        """
        try:
            members = await self.main_intent.get_joined_members(room_id=self.room_id)
        except Exception as e:
            self.log.error(e)
            return

        users: List[User] = []

        for member in members:
            user = await User.get_by_mxid(member)
            users.append(user)

        return users

    async def add_member(self, new_member: UserID):
        """If the config value for `acd.queue.user_add_method` is `join`, then join the user,
        otherwise invite the user

        Parameters
        ----------
        new_member : UserID
            The user ID of the user to add to the queue.

        """
        if self.config["acd.queues.user_add_method"] == "join":
            await self.join_user(user_id=new_member)
        else:
            await self.invite_user(user_id=new_member)

    async def remove_member(self, member: UserID, reason: str = None):
        """If the config value for "acd.remove_method" is "leave", then leave the user,
        otherwise kick the user

        Parameters
        ----------
        member : UserID
            The user ID of the member to remove.
        reason : str
            The reason for the removal.

        """
        if self.config["acd.remove_method"] == "leave":
            await self.leave_user(user_id=member, reason=reason)
        else:
            await self.kick_user(user_id=member, reason=reason)

    async def get_formatted_room_id(self) -> str:
        """It returns a string that contains the room ID, but with a link to the room

        Returns
        -------
            A string with the room_id in a link.

        """
        return f"[{self.room_id}](https://matrix.to/#/{self.room_id})"

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
        await self.main_intent.send_text(
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
        await self.main_intent.send_notice(
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
            content["body"] = new_body or text
            content["formatted_body"] = ""

        await self.main_intent.send_message(
            room_id=self.room_id,
            content=content,
        )

    async def get_info(self) -> Dict:
        """It gets the room's information

        Returns
        -------
            A dictionary of the room's information.
        """
        intent = self.main_intent if not self.main_intent.bot else self.main_intent.bot
        try:
            return await intent.api.request(
                method=Method.GET, path=SynapseAdminPath.v1.rooms[self.room_id]
            )
        except Exception as e:
            self.log.exception(e)
            return
