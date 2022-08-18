from mautrix.bridge.config import BaseBridgeConfig
from mautrix.util.config import ConfigUpdateHelper


class Config(BaseBridgeConfig):
    """Esta en una instancia del archivo config.yaml (uso el patrón singleton, para no tener muchas instancias)"""

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        # Se deben poner los campos que no deben cambiar
        # esto hace que cuando actualicemos en config.yaml
        super().do_update(helper)
        copy, copy_dict, base = helper
        copy("bridge.bot_user_id")
        copy("bridge.prefix")
        copy("bridge.invitees_to_rooms")
        copy("bridge.username_template")
        copy_dict("utils")
        copy_dict("utils.business_hours")
        copy("utils.message_bot_war")
        copy_dict("ikono_api")
        copy("bridge.command_prefix")
        copy("bridge.provisioning.admin")
        copy("appservice.email")
        if base["appservice.puppet_password"] == "generate":
            base["appservice.puppet_password"] = self._new_token()
        copy_dict("bridges.mautrix")
        copy_dict("bridges.instagram")
        copy_dict("bridges.instagram.provisioning")
        copy("bridges.plugin")
        copy("acd.keep_room_name")
        copy("acd.numbers_in_rooms")
        copy("acd.force_join")
        copy("acd.agent_invite_timeout")
        copy("acd.search_pending_rooms_interval")
        copy("acd.frontend_command_prefix")
        copy("acd.transfer_message")
        copy("acd.joined_agent_message")
        copy("acd.supervisors_to_invite.invite")
        copy("acd.supervisors_to_invite.invitees")
        copy("acd.supervisors_to_invite.power_level")
        copy("acd.voice_call.call_message")
        copy("acd.offline_agent_action")
        copy("acd.offline_agent_timeout")
        copy("acd.offline_agent_message")
        copy("acd.no_agents_for_transfer")
        copy_dict("acd.resolve_chat")
