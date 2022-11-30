import os
import random
import string
import time
from typing import Dict, List

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from mautrix.appservice import IntentAPI
from mautrix.util.async_db import Database
from pytest_mock import MockerFixture

from ..commands.handler import CommandEvent, CommandProcessor
from ..config import Config
from ..db import upgrade_table
from ..queue import Queue
from ..queue_membership import QueueMembership
from ..room_manager import RoomManager
from ..user import User
from ..util import Util

load_dotenv()


@pytest_asyncio.fixture
async def config():
    _config = Config(
        path="acd_appservice/example-config.yaml",
        registration_path="registration.yaml",
        base_path=".",
    )

    _config.load()

    return _config


@pytest_asyncio.fixture
async def db(config: Config):
    try:
        test_db_url = os.getenv("DB_TEST_URL")
    except KeyError:
        pytest.skip("Skipped Postgres tests (DB_TEST_URL not specified)")

    test_db_args: dict = config["appservice.database_opts"]

    conn: asyncpg.Connection = await asyncpg.connect(test_db_url)
    schema_name = "".join(random.choices(string.ascii_lowercase, k=8))
    schema_name = f"test_schema_{schema_name}_{int(time.time())}"
    await conn.execute(f"CREATE SCHEMA {schema_name}")

    test_db_args["server_settings"] = {"search_path": schema_name}

    database_connection = Database.create(
        test_db_url,
        upgrade_table=upgrade_table,
        db_args=test_db_args,
    )

    await database_connection.start()

    yield database_connection

    await database_connection.stop()
    await conn.execute(f"DROP SCHEMA {schema_name} CASCADE")
    await conn.close()


@pytest_asyncio.fixture
async def fake_acd_init(config: Config, db: Database):

    for table in [User, Queue, QueueMembership]:
        table.db = db
        table.config = config
        table.az = None


@pytest_asyncio.fixture
async def util(config: Config):
    return Util(config=config)


@pytest_asyncio.fixture
async def room_manager_mock(config: Config):
    return RoomManager(puppet_pk=14, control_room_id="!asvqgqpHdym:matrix.org", config=config)


@pytest_asyncio.fixture
async def get_room_info_mock(mocker, room_manager_mock: RoomManager):

    room_info = {
        "room_id": "!mscvqgqpHYjBGDxNym:matrix.org",
        "name": "The big bang Theory",
        "avatar": "mxc://matrix.org/AQDaVFlbkQoErdOgqWRgiGSV",
        "topic": "Theory, Composition, Notation, Analysis",
        "canonical_alias": "#thebigbangtheory:matrix.org",
        "joined_members": 2,
        "joined_local_members": 2,
        "joined_local_devices": 2,
        "version": "1",
        "creator": "@foo:matrix.org",
        "encryption": None,
        "federatable": True,
        "public": True,
        "join_rules": "invite",
        "guest_access": None,
        "history_visibility": "shared",
        "state_events": 93534,
    }
    room_manager_mock.ROOMS["!mscvqgqpHYjBGDxNym:matrix.org"] = room_info
    mocker.patch.object(RoomManager, "get_room_info", room_info)


@pytest_asyncio.fixture
async def intent(
    mocker: MockerFixture,
) -> User:
    mocker.patch.object(
        IntentAPI, "create_room", return_value="!asjfhjkvvkjktgasd:dominio_cliente.com"
    )
    mocker.patch.object(IntentAPI, "send_message", return_value="")
    return IntentAPI


@pytest_asyncio.fixture
async def processor(
    config: Config,
    intent: IntentAPI,
    mocker: MockerFixture,
) -> CommandProcessor:
    mocker.patch.object(CommandEvent, "reply", return_value="")
    return CommandProcessor(config=config)


@pytest_asyncio.fixture
async def admin_user(
    fake_acd_init,
    intent: IntentAPI,
) -> User:
    return await User.get_by_mxid("@admin:dominio_cliente.com")


@pytest_asyncio.fixture
async def agent_user(
    fake_acd_init,
    intent: IntentAPI,
) -> User:
    return await User.get_by_mxid("@agent1:dominio_cliente.com")


@pytest_asyncio.fixture
async def queues(
    db: Database,
    agent_user: User,
    processor: CommandProcessor,
    admin_user: User,
    intent: IntentAPI,
):

    queues: List = []
    for x in range(3):
        args = ["create", f"queue {x}", agent_user.mxid, f"Test queue {x}"]
        result: Dict = await processor.handle(
            sender=admin_user,
            command="queue",
            args_list=args,
            intent=intent,
            is_management=True,
        )

        test_queue: Queue = await Queue.get_by_room_id(result.get("data").get("room_id"))
        await QueueMembership.get_by_queue_and_user(agent_user.id, test_queue.id)
        queues.append(result.get("data"))

    return queues
