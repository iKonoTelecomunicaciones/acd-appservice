from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, AsyncGenerator, AsyncIterable, Awaitable, List, cast

from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import IntentAPI
from mautrix.bridge import BasePuppet, async_getter_lock
from mautrix.types import ContentURI, RoomID, SyncToken, UserID
from mautrix.util.simple_template import SimpleTemplate
from yarl import URL

from .agent_manager import AgentManager
from .config import Config
from .db import Puppet as DBPuppet
from .enqueued_portals import EnqueuedPortals
from .portal import Portal
from .room_manager import RoomManager

if TYPE_CHECKING:
    from .__main__ import ACDAppService


class Puppet(DBPuppet, BasePuppet):
    """Representa al usuario en el synapse."""

    by_pk: dict[int, Puppet] = {}
    by_custom_mxid: dict[UserID, Puppet] = {}
    by_email: dict[str, Puppet] = {}
    by_phone: dict[str, Puppet] = {}
    by_control_room_id: dict[RoomID, Puppet] = {}

    hs_domain: str
    mxid_template: SimpleTemplate[int]

    config: Config

    default_mxid_intent: IntentAPI
    default_mxid: UserID

    CONTROL_ROOMS: List[RoomID] = []

    # ROOMS INITIALIZED BY PM
    BIC_ROOMS: set = set()

    # Sala de control del puppet
    control_room_id: RoomID

    def __init__(
        self,
        pk: int | None = None,
        email: int | None = None,
        phone: str | None = None,
        bridge: str | None = None,
        destination: str | None = None,
        photo_mxc: ContentURI | None = None,
        name_set: bool = False,
        avatar_set: bool = False,
        is_registered: bool = False,
        custom_mxid: UserID | None = None,
        access_token: str | None = None,
        next_batch: SyncToken | None = None,
        base_url: URL | None = None,
        control_room_id: RoomID | None = None,
    ) -> None:
        super().__init__(
            pk=pk,
            email=email,
            phone=phone,
            bridge=bridge,
            destination=destination,
            name_set=name_set,
            photo_mxc=photo_mxc,
            avatar_set=avatar_set,
            is_registered=is_registered,
            custom_mxid=custom_mxid,
            access_token=access_token,
            next_batch=next_batch,
            base_url=base_url,
            control_room_id=control_room_id,
        )
        # Aquí colocamos, a nombre de que puppet mostraremos los logs,
        # ya sea usando el mxid o el email
        # IMPORTANTE: A cada marioneta de le genera un intent para poder enviar eventos a nombre
        # de esas marionetas
        self.custom_mxid = self.get_mxid_from_id(pk)
        if custom_mxid or email:
            self.log = self.log.getChild(custom_mxid or email)
        self.default_mxid_intent = self.az.intent.user(self.custom_mxid)
        # Refresca el intent de cada marioneta
        self.intent = self._fresh_intent()
        self.room_manager = RoomManager(
            puppet_pk=self.pk,
            control_room_id=self.control_room_id,
            config=self.config,
            intent=self.intent,
            bridge=self.bridge,
        )
        self.agent_manager = AgentManager(
            puppet_pk=self.pk,
            bridge=self.bridge,
            control_room_id=self.control_room_id,
            intent=self.intent,
            config=self.config,
            room_manager=self.room_manager,
        )
        self.enqueued_portals = EnqueuedPortals(
            config=self.config,
            intent=self.intent,
            puppet_pk=self.pk,
            agent_manager=self.agent_manager,
        )

        if not self.get_tasks_by_name(self.custom_mxid):
            asyncio.create_task(
                self.enqueued_portals.process_enqueued_portals(), name=self.custom_mxid
            )
        else:
            self.log.debug(f"The task process_pending_rooms.{self.custom_mxid} already exists")

        self._add_to_cache()

    def get_tasks_by_name(self, task_name: UserID):
        """> This function returns a task object from the current event loop by name

        Parameters
        ----------
        task_name : UserID
            The name of the task you want to get.

        Returns
        -------
            A task that are currently running.

        """
        # get the current event loop
        tasks = asyncio.all_tasks()
        for task in tasks:
            if task.get_name() == task_name:
                return task
        return None

    @classmethod
    def init_cls(cls, bridge: "ACDAppService") -> AsyncIterable[Awaitable[None]]:
        cls.config = bridge.config
        cls.loop = bridge.loop
        cls.mx = bridge.matrix
        cls.az = bridge.az
        cls.hs_domain = cls.config["homeserver.domain"]
        # Este atributo permite generar un template relacionado con los namesapces de usuarios
        # separados en el registration
        cls.mxid_template = SimpleTemplate(
            cls.config["bridge.username_template"],
            "userid",
            prefix="@",
            suffix=f":{cls.hs_domain}",
            type=int,
        )
        cls.login_device_name = "ACDAppService"
        # Sincroniza cada marioneta con su cuenta en el Synapse
        return (puppet.try_start() async for puppet in cls.all_with_custom_mxid())

    @classmethod
    def init_joined_rooms(cls) -> AsyncIterable[Awaitable[None]]:
        """It returns an async iterator that yields an awaitable that will sync the joined rooms of each puppet

        Parameters
        ----------

        Returns
        -------
            An async iterator of awaitables.

        """
        return (puppet.sync_joined_rooms_in_db() async for puppet in cls.all_with_custom_mxid())

    async def sync_joined_rooms_in_db(self) -> None:
        """If a room is in the matrix, but not in the database, add it in the database.

        Returns
        -------
            A list of rooms that the puppet is in.

        """
        db_joined_rooms = await Portal.get_rooms_by_puppet(self.pk)

        if not db_joined_rooms:
            return

        matrix_joined_rooms = await self.intent.get_joined_rooms()
        if not matrix_joined_rooms:
            return

        # Checking if the mx_joined_room is in a db_joined_rooms, if it is not,
        # it adds it to the database.
        for mx_joined_room in matrix_joined_rooms:
            if not mx_joined_room in db_joined_rooms:
                if await Portal.is_portal(mx_joined_room):
                    await Portal.get_by_room_id(
                        mx_joined_room, fk_puppet=self.pk, intent=self.intent, bridge=self.bridge
                    )

    async def sync_puppet_account(self):
        """It updates the puppet account's password and email address

        Returns
        -------
        """

        data = {
            "password": self.config["appservice.puppet_password"],
        }

        if self.email:
            data["threepids"] = [
                {"medium": "email", "address": self.email},
            ]

        try:
            api = self.intent.bot.api if self.intent.bot else self.intent.api
            await api.request(
                method=Method.PUT,
                path=SynapseAdminPath.v2.users[self.custom_mxid],
                content=data,
            )
        except Exception as e:
            self.log.exception(e)

    def _add_to_cache(self) -> None:
        # Mete a cada marioneta en un dict que permite acceder de manera más rápida a las
        # instancias de cada marioneta
        self.by_pk[self.pk] = self
        if self.phone:
            self.by_phone[self.phone] = self
        if self.email:
            self.by_email[self.email] = self
        if self.custom_mxid:
            self.by_custom_mxid[self.custom_mxid] = self
        if self.control_room_id:
            self.by_control_room_id[self.control_room_id] = self

    async def reset_phone(self):
        """It deletes the user's phone number from the database,
        and then updates the user's information
        """

        if self.phone and self.phone in self.by_phone:
            del self.by_phone[self.phone]

        self.phone = ""
        await self.update()

    async def save(self) -> None:
        self._add_to_cache()
        await self.update()

    @classmethod
    async def get_by_mxid(cls, mxid: UserID, create: bool = True) -> Puppet | None:
        pk = cls.get_id_from_mxid(mxid)
        if pk:
            return await cls.get_by_pk(pk, create=create)
        return None

    @classmethod
    @async_getter_lock
    async def get_by_custom_mxid(cls, mxid: UserID) -> Puppet | None:
        try:
            return cls.by_custom_mxid[mxid]
        except KeyError:
            pass

        puppet = cast(cls, await super().get_by_custom_mxid(mxid))
        if puppet:
            puppet._add_to_cache()
            return puppet

        return None

    @classmethod
    @async_getter_lock
    async def get_by_email(cls, email: str) -> Puppet | None:
        try:
            return cls.by_email[email]
        except KeyError:
            pass

        puppet = cast(cls, await super().get_by_email(email))
        if puppet:
            puppet._add_to_cache()
            return puppet

        return None

    @classmethod
    def get_id_from_mxid(cls, mxid: UserID) -> int | None:
        return cls.mxid_template.parse(mxid)

    @classmethod
    def get_mxid_from_id(cls, pk: int) -> UserID:
        return UserID(cls.mxid_template.format_full(pk))

    @classmethod
    @async_getter_lock
    async def get_by_pk(cls, pk: int, *, email: str = None, create: bool = True) -> Puppet | None:
        try:
            return cls.by_pk[pk]
        except KeyError:
            pass

        puppet = cast(cls, await super().get_by_pk(pk))
        if puppet is not None:
            puppet._add_to_cache()
            return puppet

        if create:
            puppet = cls(pk, email)
            await puppet.insert()
            puppet._add_to_cache()
            return puppet

        return None

    @classmethod
    @async_getter_lock
    async def get_puppet_by_mxid(
        cls,
        customer_mxid: UserID,
        email: str = None,
        *,
        create: bool = True,
    ) -> Puppet | None:
        try:
            return cls.by_custom_mxid[customer_mxid]
        except KeyError:
            pass

        puppet = cast(cls, await super().get_by_custom_mxid(customer_mxid))
        if puppet is not None:
            puppet._add_to_cache()
            return puppet

        if create:
            puppet = cls(custom_mxid=customer_mxid, email=email)
            await puppet.insert()
            puppet._add_to_cache()
            return puppet

        return None

    @classmethod
    def get_puppet_userid(cls, puppet_user_id: UserID) -> int:
        """It takes a user ID and returns the user ID without the prefix

        Parameters
        ----------
        puppet_user_id : UserID
            The userid of the user that is being puppeted.

        Returns
        -------
            The userid of the puppet user.

        """
        puppet_match = re.match(cls.config["acd.acd_regex"], puppet_user_id)
        if puppet_match:
            return int(puppet_match.group("userid"))

    @classmethod
    async def get_next_puppet(cls) -> int:
        """It returns the next available puppet userid

        Parameters
        ----------

        Returns
        -------
            The next available puppet userid.

        """
        next_puppet = None
        try:
            # Obtenemos todos los UserIDs de los puppets que tengan custom_mxid
            all_puppets: list[UserID] = await cls.get_all_puppets()
            if len(all_puppets) > 0:
                # A cada UserID le sacamos el número en el que va
                # luego ordenamos la lista de menor a mayor
                all_puppets_sorted = list(
                    map(lambda x: int(re.match(cls.config["acd.acd_regex"], x)[1]), all_puppets)
                )
                all_puppets_sorted.sort()

                for i in range(0, len(all_puppets_sorted)):
                    if i < len(all_puppets_sorted) - 1:
                        if (all_puppets_sorted[i] + 1) != (all_puppets_sorted[i + 1]):
                            next_puppet = all_puppets_sorted[i] + 1
                            break

                if i == len(all_puppets_sorted) - 1:
                    next_puppet = all_puppets_sorted[i] + 1

            else:
                next_puppet = 1

        except Exception as e:
            cls.log.exception(e)

        return next_puppet

    @classmethod
    async def get_by_portal(cls, portal_room_id: RoomID):
        """Get the puppet from a customer room

        Parameters
        ----------
        portal_room_id : RoomID
            Customer room_id

        Returns
        -------
            A puppet

        """

        puppet: Puppet = None

        try:
            portal = await Portal.get_by_room_id(room_id=portal_room_id, create=False)
            if not (portal and portal.fk_puppet):
                return

            puppet = await Puppet.get_by_pk(portal.fk_puppet)
        except Exception as e:
            cls.log.exception(e)
            return

        return puppet

    @classmethod
    @async_getter_lock
    async def get_by_control_room_id(cls, control_room_id: RoomID) -> Puppet:
        """It adds the puppet to the cache

        Parameters
        ----------
        control_room_id : RoomID
            The room ID of the room that the puppet is controlling.

        Returns
        -------
            A puppet object

        """
        try:
            return cls.by_control_room_id[control_room_id]
        except KeyError:
            pass

        puppet = cast(cls, await super().get_by_control_room_id(control_room_id))
        if puppet:
            puppet._add_to_cache()
            return puppet

    @classmethod
    @async_getter_lock
    async def get_by_phone(cls, phone: str) -> Puppet | None:
        try:
            return cls.by_phone[phone]
        except KeyError:
            pass

        puppet = cast(cls, await super().get_by_phone(phone))
        if puppet:
            puppet._add_to_cache()
            return puppet

    @classmethod
    async def get_puppets_from_mautrix(cls) -> List[Puppet]:
        """Get all puppets from the database

        Parameters
        ----------

        Returns
        -------
            A list of all the puppets.
        """

        all_puppets = []

        try:
            all_puppets = await cls.get_all_puppets_from_mautrix()
        except Exception as e:
            cls.log.exception(e)
            return

        return all_puppets

    @classmethod
    async def is_control_room(cls, room_id: RoomID) -> bool:
        """If the room ID is in the list of control rooms,
        or if the room ID is in the list of control room IDs,
        then the room is a control room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to check.

        Returns
        -------
            A list of room IDs.

        """
        if room_id in cls.CONTROL_ROOMS:
            return True

        if room_id in await cls.get_control_room_ids():
            return True

        return False

    @classmethod
    async def get_control_room_ids(cls) -> List[RoomID]:
        """This function is used to get the list of control rooms from the Puppet

        Parameters
        ----------

        Returns
        -------
            A list of room ids

        """
        try:
            control_room_ids = await super().get_control_room_ids()
        except Exception as e:
            cls.log.exception(e)
            return []

        if not control_room_ids:
            return []

        cls.CONTROL_ROOMS = control_room_ids
        return control_room_ids

    async def is_another_puppet(self, phone: str) -> bool:
        """It checks if the phone number is in the by_phone dictionary.

        Parameters
        ----------
        phone : str
            The phone number of the user.

        Returns
        -------
            A boolean value.

        """

        return True if phone in self.by_phone else False

    @classmethod
    async def all_with_custom_mxid(cls) -> AsyncGenerator[Puppet, None]:
        puppets = await super().all_with_custom_mxid()
        puppet: cls
        for index, puppet in enumerate(puppets):
            try:
                yield cls.by_pk[puppet.pk]
            except KeyError:
                puppet._add_to_cache()
                yield puppet

    @classmethod
    async def all_with_custom_mxid_from_mautrix(cls) -> AsyncGenerator[Puppet, None]:
        puppets = await super().all_with_custom_mxid_from_mautrix()
        puppet: cls
        for index, puppet in enumerate(puppets):
            try:
                yield cls.by_pk[puppet.pk]
            except KeyError:
                puppet._add_to_cache()
                yield puppet

    @property
    async def menubot_id(self) -> UserID | None:
        """It gets the ID of the menubot in the control room

        Returns
        -------
            The user_id of the menubot.

        """

        members = await self.intent.get_joined_members(room_id=self.control_room_id)

        for user_id in members:
            if user_id.startswith(self.config["acd.menubot_prefix"]):
                return user_id
