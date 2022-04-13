from __future__ import annotations

from typing import (TYPE_CHECKING, AsyncGenerator, AsyncIterable, Awaitable,
                    cast)

from mautrix.bridge import BaseUser, async_getter_lock
from mautrix.types import RoomID, UserID

from acd_program.config import Config
from acd_program.db.user import User as DBUser
from acd_program.puppet import Puppet

if TYPE_CHECKING:
    from .__main__ import ACDAppService


class User(DBUser, BaseUser):
    """Representa al usuario que quiere registrarse con wpp."""

    # Diccionarios que almacenan en "cache" el contenido de la bd
    # Deberían ser aquellos datos creados o consultados mientras está en ejecución el proyecto
    by_mxid: dict[UserID, User] = {}
    by_room_id: dict[RoomID, User] = {}
    by_email_id: dict[str, User] = {}

    hs_domain: str

    config: Config

    def __init__(
        self,
        mxid: UserID,
        email: str | None = None,
        room_id: RoomID | None = None,
        management_room: RoomID | None = None,
    ) -> None:
        super().__init__(mxid=mxid, email=email, room_id=room_id, management_room=management_room)
        BaseUser.__init__(self)
        self.is_whitelisted = "admin"
        self._is_logged_in = False
        self.is_admin = False

    @classmethod
    def init_cls(cls, acd: "ACDAppService") -> AsyncIterable[Awaitable[None]]:
        # Inicializa a todos los clientes guardados en la bd y los sincroniza con sus
        # respectivos puppets
        cls.bridge = acd
        cls.config = acd.config
        cls.az = acd.az
        cls.loop = acd.loop
        return (user.connect() async for user in cls.all_logged_in())

    async def connect(self) -> None:
        # Crea tareas para cada usuario y asi se pueda sincronizar con su puppet
        self.loop.create_task(self._try_sync_puppet())

    async def _try_sync_puppet(self) -> None:

        puppet = await Puppet.get_puppet_by_mxid(self.mxid)

        try:
            if puppet.custom_mxid != self.mxid and puppet.can_auto_login(self.mxid):
                self.log.info(f"Automatically enabling custom puppet")
                await puppet.switch_mxid(access_token="auto", mxid=self.mxid)
        except Exception:
            self.log.exception("Failed to automatically enable custom puppet")

    async def get_puppet(self) -> Puppet | None:
        return await Puppet.get_puppet_by_mxid(self.mxid)

    def _add_to_cache(self) -> None:
        self.by_mxid[self.mxid] = self

    async def is_logged_in(self) -> bool:
        return self._is_logged_in

    @classmethod
    @async_getter_lock
    async def get_by_mxid(cls, mxid: UserID, *, create: bool = True) -> User | None:
        """Get a User by mxid or create User.

        Given an mxid gets a User, if create is true it creates the user

        Parameters
        ----------
        mxid
            customer user_id
        create
            if true, and the user does not exist, it will be created.

        Returns
        -------
        User
            User if successful, None otherwise.
        """
        if Puppet.get_id_from_mxid(mxid):
            return None
        try:
            return cls.by_mxid[mxid]
        except KeyError:
            pass
        mxid = Puppet.get_mxid_from_id(mxid)
        user = cast(cls, await super().get_by_mxid(mxid))
        if user is not None:
            user._add_to_cache()
            return user

        if create:
            user = cls(mxid)
            await user.insert()
            user._add_to_cache()
            return user

        return None

    @classmethod
    @async_getter_lock
    async def get_by_room_id(cls, room_id: str) -> User | None:
        """Get a User by room_id.

        Given an room_id gets a User

        Parameters
        ----------
        room_id
            User room_id

        Returns
        -------
        User
            User if successful, None otherwise.
        """
        try:
            return cls.by_room_id[room_id]
        except KeyError:
            pass

        user = cast(cls, await super().get_by_room_id(room_id))
        if user is not None:
            user._add_to_cache()
            return user

        return None

    @classmethod
    @async_getter_lock
    async def get_by_email(cls, email: str) -> User | None:
        """Get a User by email.

        Given an email gets a User

        Parameters
        ----------
        email
            User email

        Returns
        -------
        User
            User if successful, None otherwise.
        """
        try:
            return cls.by_email_id[email]
        except KeyError:
            pass

        user = cast(cls, await super().get_by_email(email))
        if user is not None:
            user._add_to_cache()
            return user

        return None

    async def save(self) -> None:
        await self.update()

    @classmethod
    async def all_logged_in(cls) -> AsyncGenerator["User", None]:
        users = await super().all_logged_in()
        user: cls
        for user in users:
            try:
                yield cls.by_mxid[user.mxid]
            except KeyError:
                user._add_to_cache()
                yield user

    # Región de mensajería :)

    async def send_command(self, cmd: str) -> None:
        """Sends a command to the user's control room.

        Parameters
        ----------
        cmd
            command to be sent
        """
        pupp = await self.get_puppet()
        cmd = f"{self.config['bridge.prefix']} {cmd}"
        event_id = await pupp.intent.send_text(room_id=self.room_id, text=cmd)
        self.log.debug(
            f"Command: {cmd} have been send to room_id {self.room_id} -> Event_id = [{event_id}]"
        )

    async def send_text_message(self, room_id: str, message: str) -> dict:
        """Send a message to a room.

        Parameters
        ----------
        room_id
            room to which the message will be sent
        message
            message to be sent

        Returns
        -------
        {"state": True, "message": "The message has been sent"}

        Otherwise

        {"state": False, "message": "The message has not been sent"}
        """
        pupp = await self.get_puppet()
        try:
            event_id = await pupp.intent.send_text(room_id=room_id, text=message)
            self.log.debug(
                f"Message: {message} have been sent to room_id {room_id} -> Event_id = [{event_id}]"
            )
        except ValueError as e:
            self.log.error(f"error: {e} - room_id {room_id}")
            return {"state": False, "message": "The message has not been sent"}

        return {"state": True, "message": "The message has been sent"}

    async def set_power_level_by_user_id(
        self, user_id: UserID, room_id: RoomID, power_level: int
    ) -> None:
        """Assign powers in a room to a user.

        Parameters
        ----------
        room_id
            room to send the power_level state event
        user_id
            user to which the power_level state event should be specified
        power_level
            level of power to be assumed
        """
        bridge_prefix = self.config["bridge.prefix"]
        cmd_set_permissions = self.config["bridge.commands.set_permissions"].format(
            mxid=user_id, power_level=power_level
        )
        set_permissions = f"{bridge_prefix} {cmd_set_permissions}"
        await self.send_text_message(room_id=room_id, message=set_permissions)

    # Fin de región de mensajería

    @classmethod
    async def user_exists(cls, email: str) -> bool:
        """Verify if the user exists.

        Given an email notify if user exists

        Parameters
        ----------
        email
            User email

        Returns
        -------
        bool
            True if user exists, otherwise False
        """

        # Se consulta si el usuario existe en la db
        user = await cls.get_by_email(email)

        if not user:
            return False

        return True


    async def get_portal_with(self):
        pass
