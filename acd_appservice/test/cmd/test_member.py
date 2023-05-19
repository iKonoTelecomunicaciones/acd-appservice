import nest_asyncio
import pytest

from ...commands.handler import CommandProcessor
from ...queue import Queue
from ...queue_membership import QueueMembership, QueueMembershipState
from ...user import User

nest_asyncio.apply()


@pytest.mark.asyncio
class TestMemberCMD:
    async def test_member_login(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> This function tests the member login command

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.state == QueueMembershipState.ONLINE
        assert response.get("status") == 200

    async def test_member_login_over_other_agent(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
    ):
        """> This function tests the member login command,
        sending in agent parameter an agent different to me.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login", "--agent", "@agent2:dominio_cliente.com"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 403

    async def test_member_login_already_login(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> The function tests that a member can login to a queue, and that if they try to login again,
        they get a message saying they are already logged in

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_logout(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """It tests the member logout command.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to logout.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "logout"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.state == QueueMembershipState.OFFLINE
        assert response.get("status") == 200

    async def test_member_logout_already_logout(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> The function tests that a member can logout to a queue, and that if they try to logout again,
        they get a message saying they are already logged out.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "logout"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_login_by_admin(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Tests that an admin can log in a member

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged in
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue object that the command is being run in
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "login", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.state == QueueMembershipState.ONLINE
        assert response.get("status") == 200

    async def test_member_login_by_admin_agent_already_login(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Test admin try to log in an agent again.

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged in
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue,
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "login", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_login_admin_can_not_login(
        self,
        admin_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> An admin user can not login to a queue

        Parameters
        ----------
        admin_user : User
            User,
        processor : CommandProcessor
            The command processor that will be used to handle the command.
        queue : Queue
            The queue object that the user is trying to join
        queue_membership : QueueMembership
            The queue membership object that the user is trying to login to.

        """

        args = ["-a", "login"]

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 403

    async def test_member_login_by_admin_membership_does_not_exist(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
    ):
        """>This function tests that an admin user cannot login a member that is not in the queue

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged in
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue that the command is being run in

        """

        args = ["-a", "login", "--agent", agent_user.mxid]

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422

    async def test_member_logout_by_admin(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Tests that an admin can log out a member

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged out
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue object that the command is being run in
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "login", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "logout", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.state == QueueMembershipState.OFFLINE
        assert response.get("status") == 200

    async def test_member_logout_by_admin_agent_already_logout(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Test admin try to log out an agent again.

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged out
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue,
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "logout", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_logout_admin_can_not_logout(
        self,
        admin_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> An admin user can not logout to a queue

        Parameters
        ----------
        admin_user : User
            User,
        processor : CommandProcessor
            The command processor that will be used to handle the command.
        queue : Queue
            The queue object that the user is trying to join
        queue_membership : QueueMembership
            The queue membership object that the user is trying to logout to.

        """

        args = ["-a", "logout"]

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 403

    async def test_member_logout_by_admin_membership_does_not_exist(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
    ):
        """>This function tests that an admin user cannot logout a member that is not in the queue

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged out
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue that the command is being run in

        """

        args = ["-a", "logout", "--agent", agent_user.mxid]

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422

    async def test_member_pause(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> This function tests the member pause command

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "-p", "LUNCH"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.paused == True
        assert queue_membership.pause_reason == "LUNCH"
        assert response.get("status") == 200

    async def test_member_pause_without_login(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> This function tests member cannot pause if member is not logged in.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "pause", "-p", "LUNCH"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422

    async def test_member_pause_over_other_agent(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
    ):
        """> This function tests the member pause command,
        sending in agent parameter an agent different to me.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "--agent", "@agent2:dominio_cliente.com", "-p", "LUNCH"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 403

    async def test_member_pause_already_pause(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> The function tests that a member can pause to a queue, and that if they try to pause again,
        they get a message saying they are already logged in

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "-p", "LUNCH"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_unpause(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """It tests the member unpause command.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to unpause.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.paused == False
        assert response.get("status") == 200

    async def test_member_unpause_without_login(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """It tests member cannot unpause if member is not logged in.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to unpause.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "pause"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422

    async def test_member_unpause_already_unpause(
        self,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> The function tests that a member can unpause to a queue, and that if they try to unpause again,
        they get a message saying they are already unpaused.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause"]
        await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause"]
        await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_pause_by_admin(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Tests that an admin can pause a member

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged in
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue object that the command is being run in
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "--agent", agent_user.mxid, "-p", "LUNCH"]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.paused == True
        assert queue_membership.pause_reason == "LUNCH"
        assert response.get("status") == 200

    async def test_member_pause_by_admin_without_login(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Tests that an admin cannot pause a member if member is not logged in

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged in
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue object that the command is being run in
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "pause", "--agent", agent_user.mxid, "-p", "LUNCH"]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422

    async def test_member_pause_by_admin_agent_already_pause(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Test admin try to pause an agent again.

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be logged in
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue,
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "--agent", agent_user.mxid, "-p", "LUNCH"]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_pause_admin_can_not_pause(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> An admin user can not pause to a queue

        Parameters
        ----------
        admin_user : User
            User,
        processor : CommandProcessor
            The command processor that will be used to handle the command.
        queue : Queue
            The queue object that the user is trying to join
        queue_membership : QueueMembership
            The queue membership object that the user is trying to pause.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "-p", "LUNCH"]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 403

    async def test_member_pause_by_admin_membership_does_not_exist(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
    ):
        """>This function tests that an admin user cannot pause a member that is not in the queue

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be paused
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue that the command is being run in

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "--agent", agent_user.mxid, "-p", "LUNCH"]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422

    async def test_member_unpause_by_admin_without_login(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Tests that an admin cannot unpause a member if member is not logged in

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be unpause
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue object that the command is being run in
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "pause"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422

    async def test_member_unpause_by_admin(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Tests that an admin can unpause a member

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be unpause
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue object that the command is being run in
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert queue_membership.paused == False
        assert response.get("status") == 200

    async def test_member_unpause_by_admin_agent_already_unpause(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """Test admin try unpause an agent again.

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be unpaused
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue,
        queue_membership : QueueMembership
            QueueMembership

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "pause", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 409

    async def test_member_unpause_admin_can_not_unpause(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
        queue_membership: QueueMembership,
    ):
        """> An admin user can not unpause to a queue

        Parameters
        ----------
        admin_user : User
            User,
        processor : CommandProcessor
            The command processor that will be used to handle the command.
        queue : Queue
            The queue object that the user is trying to join
        queue_membership : QueueMembership
            The queue membership object that the user is trying to unpaused.

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause"]

        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 403

    async def test_member_logout_by_admin_membership_does_not_exist(
        self,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Queue,
    ):
        """>This function tests that an admin user cannot unpause a member that is not in the queue

        Parameters
        ----------
        admin_user : User
            User,
        agent_user : User
            User - this is the user that will be unpaused
        processor : CommandProcessor
            CommandProcessor
        queue : Queue
            Queue - this is the queue that the command is being run in

        """

        args = ["-a", "login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )

        args = ["-a", "unpause", "--agent", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.room_id,
        )
        assert response.get("status") == 422
