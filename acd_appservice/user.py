from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional, cast

from mautrix.appservice import AppService
from mautrix.bridge import BaseUser, async_getter_lock
from mautrix.types import PresenceEventContent, PresenceState, RoomID, UserID
from mautrix.util.logging import TraceLogger

from .config import Config
from .db import User as DBUser
from .queue_membership import QueueMembership, QueueMembershipState

if TYPE_CHECKING:
    from .__main__ import ACDAppService


class User(DBUser, BaseUser):
    config: Config
    az: AppService
    loop: asyncio.AbstractEventLoop
    permission_level: str

    log: TraceLogger = logging.getLogger("acd.user")

    by_mxid: dict[UserID, User] = {}
    by_id: dict[int, User] = {}

    def __init__(self, mxid: UserID, management_room: RoomID = None, id: int = None):
        self.mxid = mxid
        super().__init__(id=id, mxid=mxid, management_room=management_room)
        BaseUser.__init__(self)
        perms = self.config.get_permissions(mxid)
        self.is_whitelisted, self.is_admin, self.permission_level = perms

    @classmethod
    def init_cls(cls, bridge: "ACDAppService") -> None:
        cls.bridge = bridge
        cls.config = bridge.config
        cls.az = bridge.az
        cls.loop = bridge.loop

    def _add_to_cache(self) -> None:
        self.by_mxid[self.mxid] = self
        self.by_id[self.id] = self

    async def get_portal_with(self):
        pass

    async def get_puppet(self):
        pass

    async def is_logged_in(self):
        pass

    @property
    def is_agent(self) -> bool:
        return True if self.mxid.startswith(self.config["acd.agent_prefix"]) else False

    @property
    def is_customer(self) -> bool:
        return bool(re.match(self.config["utils.username_regex"], self.mxid))

    @property
    def is_supervisor(self) -> bool:
        return True if self.mxid.startswith(self.config["acd.supervisor_prefix"]) else False

    @property
    def is_menubot(self) -> bool:
        return True if self.mxid.startswith(self.config["acd.menubot_prefix"]) else False

    async def is_online(self, queue_id: Optional[int] = None) -> bool:
        """If the user is online, return True. If not, return False

        Parameters
        ----------
        queue_id : Optional[int]
            The ID of the queue you want to check.
            If you don't specify this,
            it will check if the user is online in any queue.

        Returns
        -------
            A boolean value.

        """

        if self.config["acd.use_presence"]:
            state = await self.get_presence()

            if not state:
                return False

            self.log.debug(f"PRESENCE RESPONSE: [{self.mxid}] -> [{state.presence}]")
            return state.presence == PresenceState.ONLINE
        else:
            if queue_id:
                membership = await QueueMembership.get_by_queue_and_user(
                    fk_user=self.id, fk_queue=queue_id, create=False
                )

                if not membership:
                    return False

                self.log.debug(
                    f"PRESENCE RESPONSE: [{self.mxid}] -> [{membership.state.value}] in queue [{queue_id}]"
                )

                return membership.state == QueueMembershipState.ONLINE

            state = bool(
                await QueueMembership.get_count_by_user_and_state(
                    fk_user=self.id, state=QueueMembershipState.ONLINE
                )
            )
            self.log.debug(
                f"PRESENCE RESPONSE: [{self.mxid}] -> [{'online' if state else 'offline'}] in some queue"
            )
            return state

    @property
    def account_id(self) -> str | None:
        """It returns the account ID of the user, if the user is a user

        Returns
        -------
            The account id of the user.

        """
        user_match = re.match(self.config["utils.username_regex"], self.mxid)
        if user_match:
            return user_match.group("number")

    async def get_formatted_displayname(self) -> str:
        displayname = await self.get_displayname()
        return f"[{displayname}](https://matrix.to/#/{self.mxid})"

    async def get_displayname(self) -> str:
        return await self.az.intent.get_displayname(user_id=self.mxid)

    async def get_presence(self) -> PresenceEventContent:
        """This function returns the presence state of the user

        Returns
        -------
            PresenceState

        """

        self.log.debug(f"Checking presence for....... [{self.mxid}]")

        try:
            response = await self.az.intent.get_presence(self.mxid)
        except Exception as e:
            self.log.exception(e)
            return

        self.log.debug(f"Presence for....... [{self.mxid}] is [{response.presence}]")

        return response

    @classmethod
    @async_getter_lock
    async def get_by_mxid(cls, mxid: UserID, *, create: bool = True) -> User | None:
        try:
            return cls.by_mxid[mxid]
        except KeyError:
            pass

        user = cast(cls, await super().get_by_mxid(mxid))
        if user is not None:
            user._add_to_cache()
            return user

        if create:
            user = cls(mxid)
            await user.insert()
            user = await super().get_by_mxid(mxid)
            user._add_to_cache()
            return user

        return None

    @classmethod
    @async_getter_lock
    async def get_by_id(cls, id: int) -> User | None:
        try:
            return cls.by_id[id]
        except KeyError:
            pass

        user = cast(cls, await super().get_by_id(id))
        if user is not None:
            user._add_to_cache()
            return user

        return None
