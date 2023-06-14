from __future__ import annotations

from re import match
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup
from mautrix.types import RoomAlias, RoomID, UserID

from ..config import Config


class Util:
    _main_matrix_regex = "[\\w-]+:[\\w.-]"

    def __init__(self, config: Config):
        self.config = config

    def is_email(self, email: str) -> bool:
        """It checks if the email is valid

        Parameters
        ----------
        email : str
            The email address to validate.

        Returns
        -------
            A boolean value.

        """
        return False if not email else bool(match(self.config["utils.regex_email"], email))

    @classmethod
    def is_user_id(cls, user_id: UserID) -> bool:
        """It checks if the user_id is valid matrix user_id

        Parameters
        ----------
        user_id : str
            The user ID to check.

        Returns
        -------
            A boolean value.

        """
        return False if not user_id else bool(match(f"^@{cls._main_matrix_regex}+$", user_id))

    @classmethod
    def is_room_id(cls, room_id: RoomID) -> bool:
        """It checks if the room_id is valid matrix room_id

        Parameters
        ----------
        room_id : str
            The room ID to check.

        Returns
        -------
            A boolean value.

        """
        return False if not room_id else bool(match(f"^!{cls._main_matrix_regex}+$", room_id))

    @classmethod
    def is_room_alias(cls, room_alias: RoomAlias) -> bool:
        """It checks if the room_alias is valid matrix room_alias

        Parameters
        ----------
        room_alias : str
            The room alise to check.

        Returns
        -------
            A boolean value.

        """
        return (
            False if not room_alias else bool(match(f"^#{cls._main_matrix_regex}+$", room_alias))
        )

    @classmethod
    def md_to_text(cls, formatted_text: str) -> str:
        """Get a message and remove the formats html and markdown.

        Parameters
        ----------
        formatted_text
            The formatted_text to be unformatted

        Returns
        -------
        plain_text
            The plain_text, formatted_text otherwise.
        """

        if formatted_text:
            formatted_text = formatted_text.replace("<br>", "\n").replace("**", "")
            return BeautifulSoup(formatted_text, features="html.parser").text
        else:
            return formatted_text

    @classmethod
    def get_emoji_number(cls, number: str) -> str | None:
        """It takes a string of numbers and returns a string of emoji numbers

        Parameters
        ----------
        number : str
            The number you want to convert to emojis.

        Returns
        -------
            the emoji number.

        """

        emoji_number = (
            number.replace("0", "0️⃣")
            .replace("1", "1️⃣")
            .replace("2", "2️⃣")
            .replace("3", "3️⃣")
            .replace("4", "4️⃣")
            .replace("5", "5️⃣")
            .replace("6", "6️⃣")
            .replace("7", "7️⃣")
            .replace("8", "8️⃣")
            .replace("9", "9️⃣")
        )

        return emoji_number

    @classmethod
    def get_future_key(cls, room_id: RoomID, agent_id: UserID, transfer: bool = False) -> str:
        """It returns a string that is used as a key to store the future in the cache

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to transfer the user to.
        agent_id : UserID
            The user ID of the agent who is being transferred to.
        transfer : bool, optional
            If True, the key will be for a transfer. If False, the key will be for a future.

        Returns
        -------
            A string

        """
        return f"transfer-{room_id}-{agent_id}" if transfer else f"{room_id}-{agent_id}"

    @classmethod
    def create_response_data(
        cls,
        detail: str,
        status: int,
        room_id: Optional[str] = None,
        additional_info: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        json_response: Dict[str, Any] = {
            "data": {
                "detail": detail,
            },
            "status": status,
        }

        if room_id:
            json_response["data"]["room_id"] = room_id

        if additional_info:
            json_response["data"].update(additional_info)

        return json_response
