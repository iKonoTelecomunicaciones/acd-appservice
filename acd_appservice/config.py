from mautrix.bridge.config import BaseBridgeConfig
from mautrix.util.config import ConfigUpdateHelper


class Config(BaseBridgeConfig):
    """Esta en una instancia del archivo config.yaml (uso el patrón singleton, para no tener muchas instancias)"""

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        # Se deben poner los campos que no deben cambiar
        # esto hace que cuando actualicemos en config.yaml
        super().do_update(helper)
        copy, copy_dict = helper.copy, helper.copy_dict
        copy("bridge.bot_user_id")
        copy("bridge.prefix")
        copy("bridge.invitees_to_rooms")
        copy("bridge.username_template")
        copy("utils.wait_promise_time")
        copy("bridge.command_prefix")
        copy_dict("bridges")
        copy_dict("bridge.management_room_text")
        copy("acd.force_name_change")
        copy("acd.control_room_id")
        copy_dict("acd.menubot")
        copy_dict("acd.menubots")
        copy("acd.force_join")
