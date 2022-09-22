import asyncio

from mautrix.types import UserID

from . import VERSION
from .acd_program import ACD
from .config import Config
from .db import init as init_db
from .db import upgrade_table
from .http_client import ProvisionBridge
from .matrix_handler import MatrixHandler
from .puppet import Puppet
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
        self.provisioning_api = ProvisioningAPI(config=self.config)
        # Usan la app de aiohttp, creamos una subaplicacion especifica para la API
        self.az.app.add_subapp(api_route, self.provisioning_api.app)

        # Iniciamos la aplicación
        await super().start()

        self.matrix.config = self.config

        asyncio.create_task(self.checking_whatsapp_connection())

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
        bridge_connector = ProvisionBridge(config=self.config)
        while True:
            try:
                all_puppets = await Puppet.get_puppets_from_mautrix()
                for puppet_id in all_puppets:
                    puppet: Puppet = await Puppet.get_by_custom_mxid(puppet_id)
                    bridge_connector.session = puppet.intent.api.session
                    response = await bridge_connector.mautrix_ping(user_id=puppet_id)
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

                        # Actualizamos el numero registrado para este puppet
                        # sin el +
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
                        # Actualizamos en blanco el número del puppet
                        puppet.phone = None
                        await puppet.save()

            except Exception as e:
                self.log.exception(e)

            await asyncio.sleep(self.config["utils.wait_ping_time"])


# Se corre la aplicación
ACDAppService().run()
