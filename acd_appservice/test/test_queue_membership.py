import nest_asyncio
import pytest

nest_asyncio.apply()


@pytest.mark.asyncio
@pytest.mark.skip
class TestQueueMembership:
    async def test_now(self):
        pass

    async def test_insert(self):
        pass

    async def test_update(self):
        pass

    async def test_delete(self):
        pass

    async def test_get_by_queue_and_user(self):
        pass

    async def test_get_by_queue_and_user_create(self):
        pass

    async def test_get_serialized_memberships(self):
        pass

    async def test_get_count_by_queue_and_state(self):
        pass

    async def test_get_count_by_user_and_state(self):
        pass

    async def test_get_by_queue(self):
        pass

    async def test_get_user_memberships(self):
        pass

    async def test_get_members(self):
        pass
