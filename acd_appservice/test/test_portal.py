import nest_asyncio
import pytest
from mautrix.types import RoomID
from pytest_mock import MockerFixture

from acd_appservice.user import User

from ..commands.handler import CommandProcessor
from ..matrix_room import MatrixRoom
from ..portal import Portal, PortalState
from ..queue import Queue
from ..queue_membership import QueueMembership, QueueMembershipState

nest_asyncio.apply()


@pytest.mark.asyncio
class TestPortal:
    async def test_get_by_room_id(self, acd_init):
        """Gets a portal object given the room_id"""

        # Create a puppet in database
        query = "INSERT INTO puppet (custom_mxid) values ($1) RETURNING pk"
        await Portal.db.execute(query, "@acd1:example.com")

        room_id: RoomID = "!qVKwlyUXOCrBfZJOdh:example.com"
        await Portal.get_by_room_id(room_id=room_id, fk_puppet=1)
        portal: Portal = await Portal.get_by_room_id(room_id=room_id, create=False)

        assert portal.room_id == room_id

    async def test_get_by_room_id_create(self, acd_init):
        """
        It tries to get a portal to the database,
        if it doesn't exist, it creates a portal in database
        """

        # Create a puppet in database
        query = "INSERT INTO puppet (custom_mxid) values ($1) RETURNING pk"
        await Portal.db.execute(query, "@acd1:example.com")

        room_id: RoomID = "!qVKwlyUXOCrBfZJOdh:example.com"
        portal: Portal = await Portal.get_by_room_id(room_id=room_id, fk_puppet=1)

        assert portal.room_id == room_id

    async def test_update_state(self, acd_init):
        """Updates the portal conversation state"""

        # Create a puppet in database
        query = "INSERT INTO puppet (custom_mxid) values ($1) RETURNING pk"
        await Portal.db.execute(query, "@acd1:example.com")

        room_id: RoomID = "!qVKwlyUXOCrBfZJOdh:example.com"
        portal: Portal = await Portal.get_by_room_id(room_id=room_id, fk_puppet=1)

        await portal.update_state(PortalState.ENQUEUED)

        assert portal.state == PortalState.ENQUEUED

    async def test_get_current_agent(
        self, customer: User, agent_user: User, supervisor: User, mocker: MockerFixture
    ):
        """Returns the agent who is currently assigned to the portal"""

        mocker.patch.object(
            MatrixRoom,
            "get_joined_users",
            return_value=[customer, agent_user, supervisor],
        )

        # Create a puppet in database
        query = "INSERT INTO puppet (custom_mxid) values ($1) RETURNING pk"
        await Portal.db.execute(query, "@acd1:example.com")

        room_id: RoomID = "!qVKwlyUXOCrBfZJOdh:example.com"
        portal: Portal = await Portal.get_by_room_id(room_id=room_id, fk_puppet=1)

        agent: User = await portal.get_current_agent()

        assert agent.mxid == agent_user.mxid

    async def test_has_online_agents(
        self,
        customer: User,
        agent_user: User,
        supervisor: User,
        mocker: MockerFixture,
        admin_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Checks if there is any online agent in the portal"""

        mocker.patch.object(
            MatrixRoom,
            "get_joined_users",
            return_value=[customer, agent_user, supervisor],
        )

        # Create a puppet in database
        query = "INSERT INTO puppet (custom_mxid) values ($1) RETURNING pk"
        await Portal.db.execute(query, "@acd1:example.com")

        room_id: RoomID = "!qVKwlyUXOCrBfZJOdh:example.com"
        portal: Portal = await Portal.get_by_room_id(room_id=room_id, fk_puppet=1)

        args = ["login", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        mocker.patch.object(
            User,
            "is_online",
            return_value=queue_membership.state == QueueMembershipState.ONLINE,
        )

        response = await portal.has_online_agents()

        assert response == True

    async def test_has_not_online_agents(
        self,
        customer: User,
        agent_user: User,
        supervisor: User,
        mocker: MockerFixture,
        admin_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Checks if there is no online agent in the portal"""

        mocker.patch.object(
            MatrixRoom,
            "get_joined_users",
            return_value=[customer, agent_user, supervisor],
        )

        # Create a puppet in database
        query = "INSERT INTO puppet (custom_mxid) values ($1) RETURNING pk"
        await Portal.db.execute(query, "@acd1:example.com")

        room_id: RoomID = "!qVKwlyUXOCrBfZJOdh:example.com"
        portal: Portal = await Portal.get_by_room_id(room_id=room_id, fk_puppet=1)

        args = ["logout", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        mocker.patch.object(
            User,
            "is_online",
            return_value=queue_membership.state == QueueMembershipState.ONLINE,
        )

        response = await portal.has_online_agents()

        assert response == False

    async def test_is_portal(self):
        pass

    async def test_is_not_portal(self):
        pass
