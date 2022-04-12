from mautrix.types import UserID

from acd_program.acd import ACD
from acd_program.config import Config
from acd_program.matrix import MatrixHandler
from acd_program.puppet import Puppet
from acd_program.user import User
from acd_program.web.provisioning_api import ProvisioningAPI

from . import VERSION
from .db import init as init_db
from .db import upgrade_table


class ACDAppService(ACD):
    """Clase que inicia el proyecto, se crea una clase que hereda de ACD"""

    name = "acd-program"
    module = "acd_program"
    command = "python -m acd_program"
    description = "An appservice for the create users for WhatsApp login"
    version = "0.1"

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
        self.add_startup_actions(User.init_cls(self))
        self.add_startup_actions(Puppet.init_cls(self))
        # Definimos la ruta por la que se podrá acceder a la API
        api_route = self.config["bridge.provisioning.prefix"]
        # Creamos la instancia de ProvisioningAPI para luego crear una subapp
        self.provisioning_api = ProvisioningAPI()
        # Le damos acceso del archivo de configuración a la API
        self.provisioning_api.config = self.config
        # Usan la app de aiohttp, creamos una subaplicacion especifica para la API
        self.az.app.add_subapp(api_route, self.provisioning_api.app)
        # Iniciamos la aplicación
        await super().start()

    def prepare_stop(self) -> None:
        # Detenemos todos los puppets que se estén sincronizando con el Synapse
        for puppet in Puppet.by_custom_mxid.values():
            puppet.stop()

    # Estos métodos son  sobreescritos de la clase padre
    def is_bridge_ghost(self, user_id: UserID) -> bool:
        return bool(Puppet.get_id_from_mxid(user_id))

    async def get_double_puppet(self, user_id: UserID):
        return await Puppet.get_by_custom_mxid(user_id)

    async def get_user(self, user_id: UserID, create: bool = True) -> User:
        return await User.get_by_mxid(user_id, create=create)

    async def get_puppet(self, user_id: UserID, create: bool = False) -> Puppet:
        return await Puppet.get_by_mxid(user_id, create=create)


# Se corre la aplicación
ACDAppService().run()
