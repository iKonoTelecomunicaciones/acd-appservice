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
        copy("utils.wait_ping_time")
        copy("bridge.command_prefix")
        copy("appservice.email")
        copy_dict("bridges")
        copy("bridges.mautrix.mxid")
        copy("bridges.mautrix.provisioning.url_base")
        copy("bridges.mautrix.provisioning.shared_secret")
        copy("acd.keep_room_name")
        copy("acd.control_room_id")
        # copy_dict("acd.menubot")
        # copy_dict("acd.menubots")
        copy("acd.menubot.user_id")
        copy("acd.menubot.user_id")
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
