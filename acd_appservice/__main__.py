import asyncio

from mautrix.types import UserID

from acd_appservice.agent_manager import AgentManager

from . import VERSION
from .acd_program import ACD
from .config import Config
from .db import init as init_db
from .db import upgrade_table
from .http_client import ProvisionBridge, client
from .matrix_handler import MatrixHandler
from .puppet import Puppet
from .room_manager import RoomManager
from .web.provisioning_api import ProvisioningAPI


class ACDAppService(ACD):
    name = "acd-appservice"
    module = "acd_appservice"
    command = "python -m acd_appservice"
    description = "An appservice for Automatic Chat Distribution with diferents bridges"
    version = VERSION

    config_class = Config
    matrix_class = MatrixHandler

    config = Config
    matrix = MatrixHandler

    provisioning_api: ProvisioningAPI

    upgrade_table = upgrade_table

    def preinit(self) -> None:
        # Se llama el preinit de la clase padre, en este paso se toman los argumentos del módulo
        # python3 -m acd_program <args>
        super().preinit()

    def prepare_db(self) -> None:
        # Se prepara la bd y se hacen las migraciones definidas en db.upgrade.py
        super().prepare_db()
        # Se inicializa la bd de con las migraciones definidas
        init_db(self.db)

    async def start(self) -> None:
        # Se cargan las acciones iniciales que deberán ser ejecutadas
        self.add_startup_actions(Puppet.init_cls(self))
        # Se sincronizan las salas donde este los puppets en matrix
        # creando las salas en nuestra bd
        self.add_startup_actions(Puppet.init_joined_rooms())
        # Definimos la ruta por la que se podrá acceder a la API
        api_route = self.config["bridge.provisioning.prefix"]
        # Creamos la instancia de ProvisioningAPI para luego crear una subapp
        self.provisioning_api = ProvisioningAPI()
        # Le damos acceso del archivo de configuración a la API
        self.provisioning_api.config = self.config
        self.provisioning_api.client = client
        await self.provisioning_api.client.init_session()
        self.provisioning_api.client.config = self.config
        self.provisioning_api.bridge_connector = ProvisionBridge(
            session=self.provisioning_api.client.session, config=self.config
        )
        # Usan la app de aiohttp, creamos una subaplicacion especifica para la API
        self.az.app.add_subapp(api_route, self.provisioning_api.app)

        # Iniciamos la aplicación
        await super().start()

        self.matrix.room_manager = RoomManager(config=self.config, intent=self.az.intent)
        # El manejador de agentes debe ir despues del start para poder utilizar los intents
        # Los intents de los puppets y el bot se inicializan en el start
        self.matrix.config = self.config
        # self.matrix.agent_manager = AgentManager(
        #     room_manager=self.matrix.room_manager,
        #     intent=self.az.intent,
        # )
        # self.provisioning_api.agent_manager = self.matrix.agent_manager
        # Creamos la tarea que va revisar si las salas pendintes ya tienen a un agente para asignar
        self.add_shutdown_actions(self.provisioning_api.client.session.close())
        asyncio.create_task(self.checking_whatsapp_connection())
        # asyncio.create_task(self.matrix.agent_manager.process_pending_rooms())

    def prepare_stop(self) -> None:
        # Detenemos todos los puppets que se estén sincronizando con el Synapse
        for puppet in Puppet.by_custom_mxid.values():
            puppet.stop()

    async def get_puppet(self, user_id: UserID, create: bool = False) -> Puppet:
        return await Puppet.get_by_mxid(user_id, create=create)

    async def get_double_puppet(self, user_id: UserID):
        return await Puppet.get_by_custom_mxid(user_id)

    async def checking_whatsapp_connection(self):
        """This function checks if the puppet is connected to WhatsApp"""
        while True:
            try:
                all_puppets = await Puppet.get_puppets()
                for puppet_id in all_puppets:
                    puppet: Puppet = await Puppet.get_by_custom_mxid(puppet_id)
                    response = await self.provisioning_api.bridge_connector.ping(user_id=puppet_id)
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

            except Exception as e:
                self.log.exception(e)

            await asyncio.sleep(self.config["utils.wait_ping_time"])


# Se corre la aplicación
ACDAppService().run()
