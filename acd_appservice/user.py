from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from mautrix.appservice import AppService
from mautrix.bridge import BaseUser, async_getter_lock
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from .config import Config
from .db import User as DBUser
from .db.user import UserRoles

if TYPE_CHECKING:
    from .__main__ import ACDAppService
import re


class User(DBUser, BaseUser):
    config: Config
    az: AppService
    loop: asyncio.AbstractEventLoop
    permission_level: str

    log: TraceLogger = logging.getLogger("acd.user")

    by_mxid: dict[UserID, User] = {}
    by_id: dict[int, User] = {}

    def __init__(
        self,
        mxid: UserID,
        management_room: RoomID = None,
        id: int = None,
        role: UserRoles = None,
    ):
        self.mxid = mxid
        super().__init__(id=id, mxid=mxid, management_room=management_room, role=role)
        BaseUser.__init__(self)
        perms = self.config.get_permissions(mxid)
        self.is_whitelisted, self.is_admin, self.permission_level = perms
        self.log = self.log.getChild(mxid)

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

    @classmethod
    def init_cls(cls, bridge: "ACDAppService") -> None:
        cls.bridge = bridge
        cls.config = bridge.config
        cls.az = bridge.az
        cls.loop = bridge.loop

    async def post_init(self):
        if not self.role:
            role_map = {
                self.is_agent: UserRoles.AGENT,
                self.is_supervisor: UserRoles.SUPERVISOR,
                self.is_menubot: UserRoles.MENU,
                self.is_customer: UserRoles.CUSTOMER,
            }
            role = role_map.get(True)
            self.role = role
            await self.update()

    def _add_to_cache(self) -> None:
        self.by_mxid[self.mxid] = self
        self.by_id[self.id] = self

    async def get_portal_with(self):
        pass

    async def get_puppet(self):
        pass

    async def is_logged_in(self):
        pass

    async def formatted_displayname(self) -> str:
        displayname = await self.get_displayname()
        return f"[{displayname}](https://matrix.to/#/{self.mxid})"

    async def get_displayname(self):
        return await self.az.intent.get_displayname(user_id=self.mxid)

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
            await user.post_init()
            return user

        if create:
            user = cls(mxid)
            if user.is_menubot:
                user.role = UserRoles.MENU
            await user.insert()
            user = await super().get_by_mxid(mxid)
            user._add_to_cache()
            await user.post_init()
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
