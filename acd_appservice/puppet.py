from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator, AsyncIterable, Awaitable, cast

from mautrix.appservice import IntentAPI
from mautrix.bridge import BasePuppet, async_getter_lock
from mautrix.types import ContentURI, SyncToken, UserID
from mautrix.util.simple_template import SimpleTemplate
from yarl import URL

from .config import Config
from .db import Puppet as DBPuppet

if TYPE_CHECKING:
    from .__main__ import ACDAppService


class Puppet(DBPuppet, BasePuppet):
    """Representa al usuario en el synapse."""

    by_pk: dict[int, Puppet] = {}
    by_custom_mxid: dict[UserID, Puppet] = {}
    hs_domain: str
    mxid_template: SimpleTemplate[int]

    config: Config

    default_mxid_intent: IntentAPI
    default_mxid: UserID

    def __init__(
        self,
        pk: int | None = None,
        custom_mxid: UserID | None = None,
        name: str | None = None,
        username: str | None = None,
        photo_id: str | None = None,
        photo_mxc: ContentURI | None = None,
        name_set: bool = False,
        avatar_set: bool = False,
        is_registered: bool = False,
        access_token: str | None = None,
        next_batch: SyncToken | None = None,
        base_url: URL | None = None,
    ) -> None:
        super().__init__(
            pk=pk,
            custom_mxid=custom_mxid,
            name=name,
            username=username,
            photo_id=photo_id,
            name_set=name_set,
            photo_mxc=photo_mxc,
            avatar_set=avatar_set,
            is_registered=is_registered,
            access_token=access_token,
            next_batch=next_batch,
            base_url=base_url,
        )
        self.log = self.log.getChild(str(custom_mxid))
        # IMPORTANTE: A cada marioneta de le genera un intent para poder enviar eventos a nombre
        # de esas marionetas
        self.default_mxid_intent = self.az.intent.user(self.custom_mxid)
        # Refresca el intent de cada marioneta
        self.intent = self._fresh_intent()

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

    def _add_to_cache(self) -> None:
        # Mete a cada marioneta en un dict que permite acceder de manera más rápida a las instancias
        # de cada marioneta
        if self.custom_mxid:
            self.by_custom_mxid[self.custom_mxid] = self

    async def save(self) -> None:
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
    def get_id_from_mxid(cls, mxid: UserID) -> int | None:
        return cls.mxid_template.parse(mxid)

    @classmethod
    def get_mxid_from_id(cls, pk: int) -> UserID:
        return UserID(cls.mxid_template.format_full(pk))

    @classmethod
    @async_getter_lock
    async def get_by_pk(cls, pk, *, create: bool = True) -> Puppet | None:
        try:
            return cls.by_pk[pk]
        except KeyError:
            pass

        puppet = cast(cls, await super().get_by_pk(pk))
        if puppet is not None:
            puppet._add_to_cache()
            return puppet

        if create:
            puppet = cls(pk)
            await puppet.insert()
            puppet._add_to_cache()
            return puppet

        return None

    @classmethod
    @async_getter_lock
    async def get_puppet_by_mxid(
        cls, customer_mxid: UserID, *, create: bool = True
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
            puppet = cls(custom_mxid=customer_mxid)
            await puppet.insert()
            puppet._add_to_cache()
            print("#$#$#", puppet)
            return puppet

        return None

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
