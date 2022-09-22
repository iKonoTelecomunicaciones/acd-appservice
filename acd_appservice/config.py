from __future__ import annotations

import re
import time
from typing import Any

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
        copy_dict("bridge.puppet_control_room")
        copy("appservice.puppet_password")
        if base["appservice.puppet_password"] == "generate":
            base["appservice.puppet_password"] = self._new_token()
        copy_dict("bridges.mautrix")
        copy_dict("bridges.instagram")
        copy_dict("bridges.gupshup")
        copy_dict("bridges.plugin")
        copy("acd.namespaces")
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
        copy_dict("acd.offline")
        copy("acd.no_agents_for_transfer")
        copy_dict("acd.resolve_chat")
        copy("acd.remove_method")

    @property
    def namespaces(self) -> dict[str, list[dict[str, Any]]]:
        """
        Generate the user ID and room alias namespace config for the registration as specified in
        https://matrix.org/docs/spec/application_service/r0.1.0.html#application-services
        """
        homeserver = self["homeserver.domain"]
        regex_ph = f"regexplaceholder{int(time.time())}"
        username_format = self["bridge.username_template"].format(userid=regex_ph)
        acd_namespaces = [
            username_template.format(userid=regex_ph)
            for username_template in self["acd.namespaces"]
        ]

        users = [
            {
                "exclusive": True,
                "regex": re.escape(f"@{username_format}:{homeserver}").replace(regex_ph, ".*"),
            }
        ]

        for acd_namespace in acd_namespaces:
            users.append(
                {
                    "exclusive": False,
                    "regex": re.escape(f"@{acd_namespace}:{homeserver}").replace(regex_ph, ".*"),
                }
            )

        alias_format = (
            self["bridge.alias_template"].format(groupname=regex_ph)
            if "bridge.alias_template" in self
            else None
        )

        return {
            "users": users,
            "aliases": [
                {
                    "exclusive": True,
                    "regex": re.escape(f"#{alias_format}:{homeserver}").replace(regex_ph, ".*"),
                }
            ]
            if alias_format
            else [],
        }
