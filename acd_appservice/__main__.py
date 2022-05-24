import asyncio

from mautrix.types import UserID

from acd_appservice.agent_manager import AgentManager

from . import VERSION
from .acd_program import ACD
from .config import Config
from .db import init as init_db
from .db import upgrade_table
from .http_client import HTTPClient, ProvisionBridge
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
        self.provisioning_api.client = HTTPClient(app=self.az.app)
        await self.provisioning_api.client.init_session()
        self.provisioning_api.client.config = self.config
        self.provisioning_api.bridge_connector = ProvisionBridge(
            session=self.provisioning_api.client.session, config=self.config
        )
        # Usan la app de aiohttp, creamos una subaplicacion especifica para la API
        self.az.app.add_subapp(api_route, self.provisioning_api.app)
        self.matrix.room_manager = RoomManager(config=self.config)

        # Iniciamos la aplicación
        await super().start()

        # El manejador de agentes debe ir despues del start para poder utilizar los intents
        # Los intents de los puppets y el bot se inicializan en el start
        self.matrix.config = self.config
        self.matrix.agent_manager = AgentManager(
            room_manager=self.matrix.room_manager,
            intent=self.az.intent,
            control_room_id=self.config["acd.control_room_id"],
        )
        self.matrix.agent_manager.client = self.provisioning_api.client
        self.provisioning_api.agent_manager = self.matrix.agent_manager
        # Creamos la tarea que va revisar si las salas pendintes ya tienen a un agente para asignar
        self.add_shutdown_actions(self.provisioning_api.client.session.close())
        asyncio.create_task(self.matrix.agent_manager.process_pending_rooms())

    def prepare_stop(self) -> None:
        # Detenemos todos los puppets que se estén sincronizando con el Synapse
        for puppet in Puppet.by_custom_mxid.values():
            puppet.stop()

    async def get_puppet(self, user_id: UserID, create: bool = False) -> Puppet:
        return await Puppet.get_by_mxid(user_id, create=create)

    async def get_double_puppet(self, user_id: UserID):
        return await Puppet.get_by_custom_mxid(user_id)


# Se corre la aplicación
ACDAppService().run()
