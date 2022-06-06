from __future__ import annotations

import sys
import asyncio
from abc import abstractmethod
from typing import Optional, Type

from aiohttp import web
from mautrix.api import HTTPAPI
from mautrix.appservice import AppService, ASStateStore
from mautrix.bridge.config import BaseBridgeConfig
from mautrix.bridge.state_store.asyncpg import PgBridgeStateStore
from mautrix.client.state_store.asyncpg import PgStateStore as PgClientStateStore
from mautrix.errors import MExclusive, MUnknownToken
from mautrix.types import UserID
from mautrix.util.async_db import Database, UpgradeTable
from mautrix.util.program import Program

from .matrix_handler import MatrixHandler
from .puppet import Puppet


class ACD(Program):
    db: Database
    az: AppService
    state_store_class: Type[ASStateStore] = PgBridgeStateStore
    state_store: ASStateStore
    matrix_class: Type[MatrixHandler]
    matrix: MatrixHandler
    periodic_reconnect_task: Optional[asyncio.Task]
    config_class: Type[BaseBridgeConfig]
    config: BaseBridgeConfig
    app: web.Application
    upgrade_table: UpgradeTable

    def __init__(
        self,
        module: str = None,
        name: str = None,
        description: str = None,
        command: str = None,
        version: str = None,
        config_class: Type[BaseBridgeConfig] = None,
        matrix_class: Type[MatrixHandler] = None,
        state_store_class: Type[ASStateStore] = None,
    ) -> None:
        super().__init__(module, name, description, command, version, config_class)
        if matrix_class:
            self.matrix_class = matrix_class
        if state_store_class:
            self.state_store_class = state_store_class

    def prepare_arg_parser(self) -> None:
        super().prepare_arg_parser()
        self.parser.add_argument(
            "-g",
            "--generate-registration",
            action="store_true",
            help="generate registration and quit",
        )
        self.parser.add_argument(
            "-r",
            "--registration",
            type=str,
            default="registration.yaml",
            metavar="<path>",
            help="the path to save the generated registration to (not needed "
            "for running the bridge)",
        )

    def preinit(self) -> None:
        # Esta parte llama el preinit de la clase padre, parsea los args enviados al ejecutar
        # el módulo
        super().preinit()
        # Si entre los args viene la el arg -g, entonces se genera el registration dado el config
        if self.args.generate_registration:
            self.generate_registration()
            sys.exit(0)

    def prepare(self) -> None:
        # Esta parte llama el prepare de la clase padre
        # lo que hace es inicializar las taks definidas
        super().prepare()
        # Preparamos la conexión a la bd
        self.prepare_db()
        # Preparamos el appservice para que pueda funcionar conectado al homeserver
        self.prepare_appservice()
        # # Aqui definimos por donde vamos a registrar los handel de matrix
        self.matrix = self.matrix_class(acd_appservice=self)

    def prepare_config(self) -> None:
        # Se prepara el archivo de configuracionismo para
        self.config = self.config_class(
            self.args.config, self.args.registration, self.args.base_config
        )
        if self.args.generate_registration:
            self.config._check_tokens = False
            # Cargamos y actualizamos el config.yaml dado nuestro example.config.yaml
        self.load_and_update_config()

    def generate_registration(self) -> None:
        # Generamos el registration.yaml
        self.config.generate_registration()
        self.config.save()

    def make_state_store(self) -> None:
        if self.state_store_class is None:
            raise RuntimeError("state_store_class is not set")
        elif issubclass(self.state_store_class, PgBridgeStateStore):
            self.state_store = self.state_store_class(
                self.db, self.get_puppet, self.get_double_puppet
            )
        else:
            # Creamos nuetra conexion singleton a la bd
            self.state_store = self.state_store_class()

    def prepare_appservice(self) -> None:
        # Se hacen los pasos necesarios para que el appservice funcione bien
        self.make_state_store()
        mb = 1024**2
        if self.name not in HTTPAPI.default_ua:
            HTTPAPI.default_ua = f"{self.name}/{self.version} {HTTPAPI.default_ua}"
        self.az = AppService(
            server=self.config["homeserver.address"],
            domain=self.config["homeserver.domain"],
            verify_ssl=self.config["homeserver.verify_ssl"],
            id=self.config["appservice.id"],
            as_token=self.config["appservice.as_token"],
            hs_token=self.config["appservice.hs_token"],
            bot_localpart=self.config["appservice.bot_username"],
            default_ua=HTTPAPI.default_ua,
            log="acd.events",
            loop=self.loop,
            aiohttp_params={"client_max_size": self.config["appservice.max_body_size"] * mb},
        )

    def prepare_db(self) -> None:
        # Preparamos la bd para poder tener una conexión con ella
        if not hasattr(self, "upgrade_table") or not self.upgrade_table:
            raise RuntimeError("upgrade_table is not set")
        self.db = Database.create(
            self.config["appservice.database"],
            upgrade_table=self.upgrade_table,
            db_args=self.config["appservice.database_opts"],
        )

    async def start_db(self) -> None:
        # Iniciamos el servicio de la bd
        if hasattr(self, "db") and isinstance(self.db, Database):
            self.log.debug("Starting database...")
            await self.db.start()
            if isinstance(self.state_store, PgClientStateStore):
                await self.state_store.upgrade_table.upgrade(self.db)

    async def stop_db(self) -> None:
        if hasattr(self, "db") and isinstance(self.db, Database):
            await self.db.stop()

    async def start(self) -> None:
        await self.start_db()
        self.log.debug("Starting appservice...")
        # Definimos el host y puerto para nuestro appservice
        await self.az.start(self.config["appservice.hostname"], self.config["appservice.port"])
        try:
            # Esperamos que la conexión como appservice sé de correctamente
            await self.matrix.wait_for_connection()
        except MUnknownToken:
            self.log.critical(
                "The as_token was not accepted. Is the registration file installed "
                "in your homeserver correctly?"
            )
            sys.exit(16)
        except MExclusive:
            self.log.critical(
                "The as_token was accepted, but the /register request was not. "
                "Are the homeserver domain and username template in the config "
                "correct, and do they match the values in the registration?"
            )
            sys.exit(16)
        # Iniciamos nuestra conexión al synapse como un bot (whapibot)
        self.add_startup_actions(self.matrix.init_as_bot())
        await super().start()
        self.az.ready = True

    async def stop(self) -> None:
        await self.az.stop()
        await super().stop()
        await self.stop_db()

    @abstractmethod
    async def get_puppet(self, user_id: UserID, create: bool = False) -> Puppet | None:
        pass
