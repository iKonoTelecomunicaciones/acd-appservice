import logging
import os
import random
import string
import time

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from mautrix.appservice import IntentAPI
from mautrix.types import RoomID
from mautrix.util.async_db import Database
from pytest_mock import MockerFixture

from ..commands.handler import CommandEvent, CommandProcessor
from ..config import Config
from ..db import upgrade_table
from ..matrix_room import MatrixRoom
from ..portal import Portal
from ..puppet import Puppet
from ..queue import Queue
from ..queue_membership import QueueMembership
from ..room_manager import RoomManager
from ..user import User
from ..util import Util

logger = logging.getLogger()

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

    database = Database.create(
        test_db_url,
        upgrade_table=upgrade_table,
        db_args=test_db_args,
    )

    await database.start()

    yield database

    await database.stop()
    await conn.execute(f"DROP SCHEMA {schema_name} CASCADE")
    await conn.close()


@pytest_asyncio.fixture
async def acd_init(config: Config, db: Database):
    for table in [User, Queue, QueueMembership, Portal, Puppet]:
        table.db = db
        table.config = config
        table.az = None


@pytest_asyncio.fixture
async def util(config: Config):
    return Util(config=config)


@pytest_asyncio.fixture
async def room_manager_mock(config: Config):
    return RoomManager(
        puppet_pk=14, control_room_id="!asvqgqpHdym:matrix.org", config=config, bridge="mautrix"
    )


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
    mocker.patch.object(IntentAPI, "send_message")
    return IntentAPI


@pytest_asyncio.fixture
async def processor(
    config: Config,
    mocker: MockerFixture,
) -> CommandProcessor:
    mocker.patch.object(CommandEvent, "reply")
    return CommandProcessor(config=config)


@pytest_asyncio.fixture
async def admin_user(
    acd_init,
    mocker: MockerFixture,
) -> User:
    mocker.patch.object(
        User,
        "get_by_mxid",
        return_value=User(mxid="@admin:dominio_cliente.com", id=int(time.time())),
    )
    return await User.get_by_mxid("@admin:dominio_cliente.com")


@pytest_asyncio.fixture
async def agent_user(
    acd_init,
    mocker: MockerFixture,
) -> User:
    mocker.patch.object(
        User,
        "get_by_mxid",
        return_value=User(mxid="@agent1:dominio_cliente.com", id=int(time.time())),
    )
    return await User.get_by_mxid("@agent1:dominio_cliente.com")


@pytest_asyncio.fixture
async def matrix_room(mocker: MockerFixture) -> MatrixRoom:
    mocker.patch.object(
        MatrixRoom,
        "get_info",
        return_value={
            "room_id": "!mscvqgqpHYjBGDxNym:matrix.org",
            "name": "Mauricio Valderrama (3123456789)",
            "avatar": "mxc://matrix.org/AQDaVFlbkQoErdOgqWRgiGSV",
            "topic": "Theory, Composition, Notation, Analysis",
            "canonical_alias": "#thebigbangtheory:matrix.org",
            "joined_members": 2,
            "joined_local_members": 2,
            "joined_local_devices": 2,
            "version": "1",
            "creator": "@mxwa_3123456789:matrix.org",
            "encryption": None,
            "federatable": True,
            "public": True,
            "join_rules": "invite",
            "guest_access": None,
            "history_visibility": "shared",
            "state_events": 93534,
        },
    )
    return MatrixRoom(room_id="!mscvqgqpHYjBGDxNym:matrix.org")


@pytest_asyncio.fixture
async def customer(
    acd_init,
    intent: IntentAPI,
    mocker: MockerFixture,
) -> User:
    mocker.patch.object(
        User,
        "get_by_mxid",
        return_value=User(mxid="@mxwa_3123456789:dominio_cliente.com", id=int(time.time())),
    )
    mocker.patch.object(
        User,
        "get_displayname",
        return_value="Mauricio Valderrama",
    )
    return await User.get_by_mxid("@mxwa_3123456789:dominio_cliente.com")


@pytest_asyncio.fixture
async def menubot(
    acd_init,
    mocker: MockerFixture,
) -> User:
    mocker.patch.object(
        User,
        "get_by_mxid",
        return_value=User(mxid="@menubot1:dominio_cliente.com", id=int(time.time())),
    )
    mocker.patch.object(
        User,
        "get_displayname",
        return_value="Menubot",
    )
    return await User.get_by_mxid("@menubot1:dominio_cliente.com")


@pytest_asyncio.fixture
async def supervisor(
    acd_init,
    mocker: MockerFixture,
) -> User:
    mocker.patch.object(
        User,
        "get_by_mxid",
        return_value=User(mxid="@supervisor1:dominio_cliente.com", id=int(time.time())),
    )
    mocker.patch.object(
        User,
        "get_displayname",
        return_value="Supervisor",
    )
    return await User.get_by_mxid("@supervisor1:dominio_cliente.com")


@pytest_asyncio.fixture
async def queue(mocker: MockerFixture, intent: IntentAPI) -> Queue:
    mocker.patch.object(
        Queue,
        "get_by_room_id",
        return_value=Queue(
            id=int(time.time()), room_id="!foo:foo.com", name="test", intent=intent
        ),
    )
    return await Queue.get_by_room_id("!foo:foo.com")


@pytest_asyncio.fixture
async def queue_membership(
    agent_user: User,
    queue: Queue,
    mocker: MockerFixture,
) -> Queue:
    mocker.patch.object(
        QueueMembership,
        "get_by_queue_and_user",
        return_value=QueueMembership(
            fk_user=agent_user.id, fk_queue=queue.id, creation_date=QueueMembership.now()
        ),
    )
    return await QueueMembership.get_by_queue_and_user(fk_user=agent_user.id, fk_queue=queue.id)


@pytest_asyncio.fixture
async def db_puppet(db: Database) -> int:
    # Create a puppet in database
    query = "INSERT INTO puppet (custom_mxid) values ($1) RETURNING pk"
    return await db.fetchval(query, "@acd1:example.com")


@pytest_asyncio.fixture
async def portal(db_puppet: Puppet, acd_init) -> Portal:
    room_id: RoomID = "!qVKwlyUXOCrBfZJOdh:example.com"
    return await Portal.get_by_room_id(room_id=room_id, fk_puppet=db_puppet)
