import nest_asyncio
import pytest
from mautrix.types import RoomID
from pytest_mock import MockerFixture

from ..room_manager import RoomManager

nest_asyncio.apply()


@pytest.mark.asyncio
class TestRoomManager:
    async def test_is_mx_whatsapp_status_broadcast(
        self, mocker: MockerFixture, room_manager_mock: RoomManager
    ):
        """
        True if the room is whatsapp_status_broadcast, False otherwise.
        """
        room_name = "WhatsApp Status Broadcast"

        mocker.patch.object(RoomManager, "get_room_name", return_value=room_name)
        room_manager_mock.intent = None
        result = await room_manager_mock.is_mx_whatsapp_status_broadcast(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )

        assert result == True

    async def test_is_not_mx_whatsapp_status_broadcast(
        self, mocker: MockerFixture, room_manager_mock: RoomManager
    ):
        """
        True if the room is whatsapp_status_broadcast, False otherwise.
        """
        room_name = "SALA DE CONTROL"

        mocker.patch.object(RoomManager, "get_room_name", return_value=room_name)
        room_manager_mock.intent = None
        result = await room_manager_mock.is_mx_whatsapp_status_broadcast(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )
        assert result == False
