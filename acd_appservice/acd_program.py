from __future__ import annotations

import asyncio
import sys
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
        # It is the parent preinit, this will parse the command line arguments
        # sent to execute the module
        super().preinit()
        # If the args come between the arg -g, then the registration is generated given the config
        if self.args.generate_registration:
            self.generate_registration()
            sys.exit(0)

    def prepare(self) -> None:
        # It initializes the tasks defined
        super().prepare()
        # Prepare the database connection
        self.prepare_db()
        # Prepare the appservice so that it can work connected to the homeserver
        self.prepare_appservice()
        # Register the matrix handlers
        self.matrix = self.matrix_class(acd_appservice=self)

    def prepare_config(self) -> None:
        # Prepare the config file
        self.config = self.config_class(
            self.args.config, self.args.registration, self.args.base_config
        )
        if self.args.generate_registration:
            self.config._check_tokens = False
            # Load and update the config.yaml given our example.config.yaml
        self.load_and_update_config()

    def generate_registration(self) -> None:
        # Generate registration.yaml
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
            # Create our singleton database connection
            self.state_store = self.state_store_class()

    def prepare_appservice(self) -> None:
        # Configure the appservice
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
            ephemeral_events=self.config["appservice.ephemeral_events"],
        )

    def prepare_db(self) -> None:
        # Prepare the database connection
        if not hasattr(self, "upgrade_table") or not self.upgrade_table:
            raise RuntimeError("upgrade_table is not set")
        self.db = Database.create(
            self.config["appservice.database"],
            upgrade_table=self.upgrade_table,
            db_args=self.config["appservice.database_opts"],
        )

    async def start_db(self) -> None:
        # Start the database connection
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
        # Define the host and port for our appservice
        await self.az.start(self.config["appservice.hostname"], self.config["appservice.port"])
        try:
            # Wait the database connection as appservice is done correctly
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
        # Start our connection to synapse as a bot (ACD)
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
