import asyncio

from mautrix.types import UserID

from .acd_program import ACD
from .client import ProvisionBridge
from .commands.handler import CommandProcessor
from .commands.resolve import BulkResolve
from .config import Config
from .db import init as init_db
from .db import upgrade_table
from .matrix_handler import MatrixHandler
from .matrix_room import MatrixRoom
from .puppet import Puppet
from .user import User
from .version import linkified_version, version
from .web.provisioning_api import ProvisioningAPI


class ACDAppService(ACD):
    name = "acd-appservice"
    module = "acd_appservice"
    command = "python -m acd_appservice"
    description = "An appservice for Automatic Chat Distribution with diferents bridges"

    repo_url = "https://gitlab.com/iKono/acd-appservice"
    version = version
    markdown_version = linkified_version

    config_class = Config
    matrix_class = MatrixHandler

    config = Config
    matrix = MatrixHandler

    provisioning_api: ProvisioningAPI

    upgrade_table = upgrade_table

    def preinit(self) -> None:
        # Call the parent preinit, this will parse the command line arguments
        # python3 -m acd_program <args>
        super().preinit()

    def prepare_db(self) -> None:
        # Prepares the database and runs the migrations defined in db.upgrade.py
        super().prepare_db()
        # Initialize the database with the migrations defined
        init_db(self.db)

    async def start(self) -> None:
        # Load the initial actions that should be executed
        self.add_startup_actions(Puppet.init_cls(self))
        User.init_cls(self)
        MatrixRoom.init_cls(self)
        # Sync all the rooms where the puppets are in matrix
        # creating the rooms in our database
        self.add_startup_actions(Puppet.init_joined_rooms())
        # Define the route to access the ACD API
        api_route = self.config["bridge.provisioning.prefix"]
        # Create the ProvisioningAPI instance to create a subapp
        commands = CommandProcessor(config=self.config)
        bulk_resolve = BulkResolve(config=self.config, commands=commands)
        self.provisioning_api = ProvisioningAPI(
            config=self.config,
            loop=self.loop,
            bulk_resolve=bulk_resolve,
        )
        # Use the aiohttp app, create a specific subapplication for the API
        self.az.app.add_subapp(api_route, self.provisioning_api.app)

        # Start the application
        await super().start()

        self.matrix.commands = commands
        asyncio.create_task(self.checking_whatsapp_connection())

    def prepare_stop(self) -> None:
        # Stop all puppets that are syncing with Synapse
        for puppet in Puppet.by_custom_mxid.values():
            puppet.stop()

    async def get_puppet(self, user_id: UserID, create: bool = False) -> Puppet:
        return await Puppet.get_by_mxid(user_id, create=create)

    async def get_double_puppet(self, user_id: UserID):
        return await Puppet.get_by_custom_mxid(user_id)

    async def checking_whatsapp_connection(self):
        """This function checks if the puppet is connected to WhatsApp"""
        bridge_connector = ProvisionBridge(config=self.config)
        while True:
            try:
                all_puppets = await Puppet.get_puppets_from_mautrix()
                for puppet_id in all_puppets:
                    puppet: Puppet = await Puppet.get_by_custom_mxid(puppet_id)
                    bridge_connector.session = puppet.intent.api.session
                    status, response = await bridge_connector.ping(user_id=puppet_id)
                    # Checking if the puppet is connected to WhatsApp.
                    if (
                        not response.get("error")
                        and response.get("whatsapp").get("conn")
                        and response.get("whatsapp").get("conn").get("is_connected")
                    ):
                        self.log.info(
                            f"The user [{puppet_id}] :: [{puppet.email}]"
                            f" is correctly connected to WhatsApp ✅"
                        )
                        await puppet.intent.send_notice(
                            room_id=puppet.control_room_id,
                            text="✅ I am connected to WhastApp ✅",
                        )

                        # Update the registered number for this puppet without the +
                        puppet.phone = response.get("whatsapp").get("phone").replace("+", "")
                        await puppet.save()

                    else:
                        self.log.warning(
                            f"The user [{puppet_id}] :: [{puppet.email}]"
                            f" is not correctly connected to WhatsApp 🚫"
                        )
                        await puppet.intent.send_notice(
                            room_id=puppet.control_room_id,
                            text=f"🚫 I am not connected to WhastApp 🚫 ::"
                            f" Error {response.get('error')}",
                        )
                        # Update puppet phone number to None
                        puppet.phone = None
                        await puppet.save()

            except Exception as e:
                self.log.exception(e)

            await asyncio.sleep(self.config["utils.wait_ping_time"])


# Run the application
ACDAppService().run()
