from unittest.mock import AsyncMock, MagicMock

import nest_asyncio
import pytest
from mautrix.appservice import IntentAPI

from ..config import Config
from ..puppet import Puppet

nest_asyncio.apply()


@pytest.mark.asyncio
class TestPuppet:
    # Tests that a new Puppet instance can be created with valid parameters
    @pytest.mark.asyncio
    async def test_create_puppet_with_valid_parameters(self, config: Config, intent: IntentAPI):
        Puppet.get_mxid_from_id = AsyncMock(return_value="@acd1:dominio_cliente.com")
        Puppet.get_tasks_by_name = MagicMock(return_value="@acd1:dominio_cliente.com")
        az_mock = MagicMock()
        az_mock.intent = MagicMock()
        az_mock.intent.user().mxid = "@acd1:dominio_cliente.com"
        Puppet.az = az_mock
        Puppet.config = config
        Puppet.intent = intent
        puppet = Puppet(
            pk=1,
            email="test@dominio_cliente.com",
            phone="573123456789",
            bridge="mautrix",
            destination="@menubot1:dominio_cliente.com",
            photo_mxc="",
            name_set=True,
            avatar_set=True,
            is_registered=True,
            custom_mxid="@acd1:dominio_cliente.com",
            access_token="1234asdf",
            next_batch="",
            base_url="",
            control_room_id="!pQUpPAYbJmqPdNRhQp:dominio_cliente.com",
        )
        puppet_custom_mxid = await puppet.custom_mxid
        assert puppet_custom_mxid == "@acd1:dominio_cliente.com"
        assert puppet.pk == 1
        assert puppet.email == "test@dominio_cliente.com"
        assert puppet.phone == "573123456789"
        assert puppet.bridge == "mautrix"
        assert puppet.destination == "@menubot1:dominio_cliente.com"
        assert puppet.photo_mxc == ""
        assert puppet.name_set == True
        assert puppet.avatar_set == True
        assert puppet.is_registered == True
        assert puppet.access_token == "1234asdf"
        assert puppet.next_batch == ""
        assert puppet.base_url == ""
        assert puppet.control_room_id == "!pQUpPAYbJmqPdNRhQp:dominio_cliente.com"

    # Tests that a Puppet instance can be retrieved by its primary key
    async def test_retrieve_puppet_by_primary_key(self, config: Config, intent: IntentAPI):
        Puppet.get_mxid_from_id = AsyncMock(return_value="@acd1:dominio_cliente.com")
        Puppet.get_tasks_by_name = MagicMock(return_value="@acd1:dominio_cliente.com")
        az_mock = MagicMock()
        az_mock.intent = MagicMock()
        az_mock.intent.user().mxid = "@acd1:dominio_cliente.com"
        Puppet.az = az_mock
        Puppet.config = config
        Puppet.intent = intent
        Puppet.get_by_pk = AsyncMock(return_value=Puppet(pk=1))
        puppet = await Puppet.get_by_pk(1)
        assert puppet.pk == 1

    # Tests that a Puppet instance can be retrieved by its custom mxid
    async def test_retrieve_puppet_by_custom_mxid(self, config: Config, intent: IntentAPI):
        Puppet.get_mxid_from_id = AsyncMock(return_value="@acd1:dominio_cliente.com")
        Puppet.get_tasks_by_name = MagicMock(return_value="@acd1:dominio_cliente.com")
        az_mock = MagicMock()
        az_mock.intent = MagicMock()
        az_mock.intent.user().mxid = "@acd1:dominio_cliente.com"
        Puppet.az = az_mock
        Puppet.config = config
        Puppet.intent = intent
        Puppet.get_by_custom_mxid = AsyncMock(
            return_value=Puppet(custom_mxid="@acd1:dominio_cliente.com")
        )
        puppet = await Puppet.get_by_custom_mxid("@acd1:dominio_cliente.com")
        puppet_custom_mxid = await puppet.custom_mxid
        assert puppet_custom_mxid == "@acd1:dominio_cliente.com"

    # Tests that a Puppet instance can be retrieved by its email
    async def test_retrieve_puppet_by_email(self, config: Config, intent: IntentAPI):
        Puppet.get_mxid_from_id = AsyncMock(return_value="@acd1:dominio_cliente.com")
        Puppet.get_tasks_by_name = MagicMock(return_value="@acd1:dominio_cliente.com")
        az_mock = MagicMock()
        az_mock.intent = MagicMock()
        az_mock.intent.user().mxid = "@acd1:dominio_cliente.com"
        Puppet.az = az_mock
        Puppet.config = config
        Puppet.intent = intent
        Puppet.get_by_email = AsyncMock(return_value=Puppet(email="test@dominio_cliente.com"))
        puppet = await Puppet.get_by_email("test@dominio_cliente.com")
        assert puppet.email == "test@dominio_cliente.com"

    # Tests that a Puppet instance can be retrieved by its phone number
    async def test_retrieve_puppet_by_phone_number(self, config: Config, intent: IntentAPI):
        Puppet.get_mxid_from_id = AsyncMock(return_value="@acd1:dominio_cliente.com")
        Puppet.get_tasks_by_name = MagicMock(return_value="@acd1:dominio_cliente.com")
        az_mock = MagicMock()
        az_mock.intent = MagicMock()
        az_mock.intent.user().mxid = "@acd1:dominio_cliente.com"
        Puppet.az = az_mock
        Puppet.config = config
        Puppet.intent = intent
        Puppet.get_by_phone = AsyncMock(return_value=Puppet(phone="573123456789"))
        puppet = await Puppet.get_by_phone("573123456789")
        assert puppet.phone == "573123456789"

    # Tests that a Puppet instance can be retrieved by its control room ID
    async def test_retrieve_puppet_by_control_room_id(self, config: Config, intent: IntentAPI):
        Puppet.get_mxid_from_id = AsyncMock(return_value="@acd1:dominio_cliente.com")
        Puppet.get_tasks_by_name = MagicMock(return_value="@acd1:dominio_cliente.com")
        az_mock = MagicMock()
        az_mock.intent = MagicMock()
        az_mock.intent.user().mxid = "@acd1:dominio_cliente.com"
        Puppet.az = az_mock
        Puppet.config = config
        Puppet.intent = intent
        Puppet.get_by_control_room_id = AsyncMock(
            return_value=Puppet(control_room_id="!pQUpPAYbJmqPdNRhQp:dominio_cliente.com")
        )
        puppet = await Puppet.get_by_control_room_id("!pQUpPAYbJmqPdNRhQp:dominio_cliente.com")
        assert puppet.control_room_id == "!pQUpPAYbJmqPdNRhQp:dominio_cliente.com"
