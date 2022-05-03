
import nest_asyncio
import pytest
from mautrix.appservice import IntentAPI
from mautrix.types import RoomID
from mautrix.util.async_db import Database

from acd_appservice import room_manager

nest_asyncio.apply()


@pytest.mark.asyncio
class TestRoomManager:
    async def test_is_customer_room(
        self, mocker, room_manager_mock: room_manager.RoomManager, get_room_info_mock
    ):
        """
        True if the room is created by a client, False otherwise.
        """
        room_creator = "@mxwa_573058790290:matrix.org"

        mocker.patch.object(
            room_manager.RoomManager, "get_room_creator", return_value=room_creator
        )

        intent: IntentAPI = None
        result = await room_manager_mock.is_customer_room(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org"), intent=intent
        )
        assert result == True

    async def test_is_not_customer_room(
        self, mocker, room_manager_mock: room_manager.RoomManager, get_room_info_mock
    ):
        """
        False if the room is not created by a client, True otherwise.
        """
        room_creator = "@supervisor:matrix.org"

        mocker.patch.object(
            room_manager.RoomManager, "get_room_creator", return_value=room_creator
        )

        intent: IntentAPI = None
        result = await room_manager_mock.is_customer_room(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org"), intent=intent
        )
        assert result == False

    async def test_get_room_bridge(
        self, mocker, room_manager_mock: room_manager.RoomManager, get_room_info_mock
    ):
        """
        Returns the bridge that belongs to the room, None if the room does not have a client.
        """
        room_creator = "@mxwa_573058790290:matrix.org"

        mocker.patch.object(
            room_manager.RoomManager, "get_room_creator", return_value=room_creator
        )
        intent: IntentAPI = None
        result = await room_manager_mock.get_room_bridge(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org"), intent=intent
        )

        assert result == "mautrix"

    async def test_not_get_room_bridge(
        self, mocker, room_manager_mock: room_manager.RoomManager, get_room_info_mock
    ):
        """
        You should not return the room bridge, A bridge if the room has a client.
        """
        room_creator = "@agente:matrix.org"

        mocker.patch.object(
            room_manager.RoomManager, "get_room_creator", return_value=room_creator
        )
        intent: IntentAPI = None
        result = await room_manager_mock.get_room_bridge(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org"), intent=intent
        )

        assert result == None

    async def test_is_mx_whatsapp_status_broadcast(
        self, mocker, room_manager_mock: room_manager.RoomManager
    ):
        """
        True if the room is whatsapp_status_broadcast, False otherwise.
        """
        room_name = "WhatsApp Status Broadcast"

        mocker.patch.object(room_manager.RoomManager, "get_room_name", return_value=room_name)
        intent: IntentAPI = None
        result = await room_manager_mock.is_mx_whatsapp_status_broadcast(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org"), intent=intent
        )

        assert result == True

    async def test_is_not_mx_whatsapp_status_broadcast(
        self, mocker, room_manager_mock: room_manager.RoomManager
    ):
        """
        True if the room is whatsapp_status_broadcast, False otherwise.
        """
        room_name = "SALA DE CONTROL"

        mocker.patch.object(room_manager.RoomManager, "get_room_name", return_value=room_name)
        intent: IntentAPI = None
        result = await room_manager_mock.is_mx_whatsapp_status_broadcast(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org"), intent=intent
        )
        assert result == False

    async def test_get_update_name(self, mocker, room_manager_mock: room_manager.RoomManager):
        """
        Returns the updated name of a client's room.
        """
        new_room_name = "Alejandro Herrera (WA) (573058790293)"
        mocker.patch.object(
            room_manager.RoomManager, "create_room_name", return_value=new_room_name
        )
        intent: IntentAPI = None
        result = await room_manager_mock.get_update_name(
            creator="@mxwa_573058790293", intent=intent
        )
        assert result == "Alejandro Herrera  (573058790293)"
