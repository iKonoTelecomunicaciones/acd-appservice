from mautrix.bridge.config import BaseBridgeConfig
from mautrix.util.config import ConfigUpdateHelper


class Config(BaseBridgeConfig):
    """Esta en una instancia del archivo config.yaml (uso el patrón singleton, para no tener muchas instancias)"""

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        # Se deben poner los campos que no deben cambiar
        # esto hace que cuando actualicemos en config.yaml
        super().do_update(helper)
        copy = helper.copy
        copy("bridge.bot_user_id")
        copy("bridge.prefix")
        copy("bridge.invitees_to_rooms")
        copy("bridge.username_template")
        copy("utils.wait_promise_time")
        copy("bridge.command_prefix")
