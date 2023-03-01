import nest_asyncio
import pytest

nest_asyncio.apply()
from ..user import User


@pytest.mark.asyncio
class TestUser:
    # async def test_insert(self):
    #     pass

    # async def test_update(self):
    #     pass

    # async def test_delete(self):
    #     pass

    # async def test_get_by_mxid(self):
    #     pass

    # async def test_get_id(self):
    #     pass

    # async def test_get_by_mxid_create(self):
    #     pass

    async def test_is_agent(self, agent_user: User):
        assert agent_user.is_agent == True

    async def test_is_not_agent(self, admin_user: User):
        assert admin_user.is_agent != True

    async def test_is_customer(self, customer: User):
        assert customer.is_customer == True

    async def test_is_not_customer(self, agent_user: User):
        assert agent_user.is_customer != True

    async def test_is_supervisor(self, supervisor: User):
        assert supervisor.is_supervisor == True

    async def test_is_not_supervisor(self, customer: User):
        assert customer.is_supervisor != True

    async def test_is_menubot(self, menubot: User):
        assert menubot.is_menubot == True

    async def test_is_not_menubot(self, supervisor: User):
        assert supervisor.is_menubot != True

    async def test_is_admin(self, admin_user: User, customer: User):
        assert admin_user.is_admin == True
        assert customer.is_admin != True

    async def test_is_not_admin(self, agent_user: User, customer: User):
        assert agent_user.is_admin != True
        assert customer.is_admin != True

    # async def test_is_online(self):
    #     pass

    # async def test_is_not_online(self):
    #     pass

    async def test_get_account_id(self, customer: User):
        assert "3123456789" == customer.account_id

    async def test_get_formatted_displayname(self, customer: User):
        assert (
            f"[{await customer.get_displayname()}](https://matrix.to/#/{customer.mxid})"
            == await customer.get_formatted_displayname()
        )

    async def test_get_displayname(self, customer: User):
        assert "Mauricio Valderrama" == await customer.get_displayname()
