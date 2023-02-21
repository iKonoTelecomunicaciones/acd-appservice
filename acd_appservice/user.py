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

    def __init__(
        self, mxid: UserID, management_room: RoomID = None, id: int = None, role: str = None
    ):
        self.mxid = mxid
        super().__init__(id=id, mxid=mxid, management_room=management_room, role=role)
        BaseUser.__init__(self)
        perms = self.config.get_permissions(mxid)
        self.is_whitelisted, self.is_admin, self.permission_level = perms
        self.log = self.log.getChild(mxid)

    @property
    def is_menubot(self) -> bool:
        """This function checks if the user_id starts with the menubot prefix
        defined in the config file

        Parameters
        ----------
        user_id : UserID
            The user ID of the user to check.

        Returns
        -------
            A boolean value.

        """
        return bool(self.mxid.startswith(self.config["acd.menubot_prefix"]))

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
