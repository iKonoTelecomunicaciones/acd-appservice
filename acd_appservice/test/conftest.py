import pytest_asyncio

from ..config import Config
from ..room_manager import RoomManager
from ..util import Util


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
