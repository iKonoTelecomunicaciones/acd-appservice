from __future__ import annotations

from re import match

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
            formatted_text = (
                formatted_text.replace("<br>", "\n")
                .replace("<p>", "\n")
                .replace("</p>", "\n")
                .replace("**", "")
            )
            plain_text = BeautifulSoup(formatted_text, features="html.parser").text
            return plain_text
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
