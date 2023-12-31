from __future__ import annotations

import re
import time
from typing import Any, NamedTuple

from mautrix.bridge.config import BaseBridgeConfig
from mautrix.client import Client
from mautrix.types import UserID
from mautrix.util.config import ConfigUpdateHelper, ForbiddenDefault, ForbiddenKey

Permissions = NamedTuple("Permissions", user=bool, admin=bool, level=str)


class Config(BaseBridgeConfig):
    """Esta en una instancia del archivo config.yaml (uso el patrón singleton, para no tener muchas instancias)"""

    @property
    def forbidden_defaults(self) -> list[ForbiddenDefault]:
        return [
            *super().forbidden_defaults,
            ForbiddenDefault("appservice.database", "postgres://username:password@hostname/db"),
            ForbiddenDefault("bridge.permissions", ForbiddenKey("example.com")),
        ]

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        # You must put the fields that should not change
        # this makes that when we update in config.yaml
        super().do_update(helper)
        copy, copy_dict, base = helper

        # Bridge
        copy("bridge.bot_user_id")
        copy("bridge.prefix")
        copy("bridge.invitees_to_rooms")
        copy("bridge.username_template")
        copy("bridge.command_prefix")
        copy_dict("bridge.puppet_control_room")
        copy_dict("bridge.permissions")

        # AppService
        copy("appservice.puppet_password")
        if base["appservice.puppet_password"] == "generate":
            base["appservice.puppet_password"] = self._new_token()

        # Bridges
        copy("bridges.mautrix.mxid")
        copy("bridges.mautrix.provisioning.url_base")
        copy("bridges.mautrix.provisioning.shared_secret")
        copy("bridges.mautrix.initial_state.enabled")
        copy_dict("bridges.mautrix.initial_state.power_levels")

        copy("bridges.instagram.mxid")
        copy("bridges.instagram.provisioning.url_base")
        copy("bridges.instagram.provisioning.shared_secret")
        copy("bridges.instagram.initial_state.enabled")
        copy_dict("bridges.instagram.initial_state.power_levels")

        copy("bridges.facebook.mxid")
        copy("bridges.facebook.provisioning.url_base")
        copy("bridges.facebook.provisioning.shared_secret")
        copy("bridges.facebook.initial_state.enabled")
        copy_dict("bridges.facebook.initial_state.power_levels")

        copy("bridges.gupshup.mxid")
        copy("bridges.gupshup.provisioning.url_base")
        copy("bridges.gupshup.provisioning.shared_secret")
        copy("bridges.gupshup.initial_state.enabled")
        copy_dict("bridges.gupshup.initial_state.power_levels")

        copy("bridges.chatterbox.initial_state.enabled")
        copy_dict("bridges.chatterbox.initial_state.power_levels")

        copy("bridges.meta_instagram.mxid")
        copy("bridges.meta_instagram.provisioning.url_base")
        copy("bridges.meta_instagram.provisioning.shared_secret")
        copy("bridges.meta_instagram.initial_state.enabled")
        copy_dict("bridges.meta_instagram.initial_state.power_levels")

        copy("bridges.meta_facebook.mxid")
        copy("bridges.meta_facebook.provisioning.url_base")
        copy("bridges.meta_facebook.provisioning.shared_secret")
        copy("bridges.meta_facebook.initial_state.enabled")
        copy_dict("bridges.meta_facebook.initial_state.power_levels")

        # ACD
        copy("acd.namespaces")
        copy("acd.keep_room_name")
        copy("acd.numbers_in_rooms")
        copy("acd.agent_invite_timeout")
        copy("acd.frontend_command_prefix")
        copy("acd.transfer_message")
        copy("acd.joined_agent_message")
        copy("acd.unavailable_agent_in_transfer")
        copy("acd.supervisors_to_invite.invite")
        copy("acd.supervisors_to_invite.invitees")
        copy("acd.supervisors_to_invite.power_level")
        copy("acd.voice_call.call_message")
        copy("acd.voice_call.no_voice_call")
        copy_dict("acd.offline")
        copy("acd.no_agents_for_transfer")
        copy_dict("acd.resolve_chat")
        copy("acd.bulk_resolve.block_size")
        copy("acd.available_agents_room")
        copy("acd.queues.visibility")
        copy("acd.enqueued_portals.portals_per_agent")
        copy("acd.enqueued_portals.max_iterations")
        copy("acd.enqueued_portals.min_time")
        copy("acd.enqueued_portals.search_pending_rooms_interval")
        copy("acd.queues.invitees")
        copy("acd.use_presence")
        copy_dict("acd.access_methods")

        # Utils
        copy_dict("utils")
        copy_dict("utils.business_hours")
        copy("utils.message_bot_war")

        # Third-party APIs
        copy_dict("ikono_api")

        # NATS
        copy_dict("nats")

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

    def _get_permissions(self, key: str) -> Permissions:
        level = self["bridge.permissions"].get(key, "")
        admin = level == "admin"
        user = level == "user" or admin
        return Permissions(user, admin, level)

    def get_permissions(self, mxid: UserID) -> Permissions:
        permissions = self["bridge.permissions"]
        if mxid in permissions:
            return self._get_permissions(mxid)

        _, homeserver = Client.parse_user_id(mxid)
        if homeserver in permissions:
            return self._get_permissions(homeserver)

        return self._get_permissions("*")
