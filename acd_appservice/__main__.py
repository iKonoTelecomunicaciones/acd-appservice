import asyncio

import ptvsd
from mautrix.types import UserID

from acd_appservice.agent_manager import AgentManager

from .acd_program import ACD
from .config import Config
from .db import init as init_db
from .db import upgrade_table
from .matrix_handler import MatrixHandler
from .puppet import Puppet
from .room_manager import RoomManager
from .web.provisioning_api import ProvisioningAPI

ptvsd.enable_attach(address=("0.0.0.0", 5678))


class ACDAppService(ACD):
    name = "acd-appservice"
    module = "acd_appservice"
    command = "python -m acd_appservice"
    description = "An appservice for Automatic Chat Distribution with diferents bridges"
    version = "0.0.0"

    config_class = Config
    matrix_class = MatrixHandler

    config = Config
    matrix = MatrixHandler

    room_manager = RoomManager
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
        # Definimos la ruta por la que se podrá acceder a la API
        api_route = self.config["bridge.provisioning.prefix"]
        # Creamos la instancia de ProvisioningAPI para luego crear una subapp
        self.provisioning_api = ProvisioningAPI()
        # Le damos acceso del archivo de configuración a la API
        self.provisioning_api.config = self.config

        # Usan la app de aiohttp, creamos una subaplicacion especifica para la API
        self.az.app.add_subapp(api_route, self.provisioning_api.app)
        self.matrix.room_manager = RoomManager(config=self.config)
        self.room_manager = self.matrix.room_manager

        # Iniciamos la aplicación
        await super().start()

        # El manejador de agentes debe ir despues del start para poder utilizar los intents
        # Los intents de los puppets y el bot se inicializan en el start
        self.matrix.agent_manager = AgentManager(
            acd_appservice=self,
            intent=self.az.intent,
            control_room_id=self.config["acd.control_room_id"],
        )
        # Registramos el bot principal en la tabla de puppet
        await Puppet.get_puppet_by_mxid(self.az.intent.mxid)
        # Creamos la tarea que va revisar si las salas pendintes ya tienen a un agente para asignar
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
