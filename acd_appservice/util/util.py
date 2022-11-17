from re import match

from bs4 import BeautifulSoup

from ..config import Config


class Util:
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
        return bool(match(self.config["utils.regex_email"], email))

    @classmethod
    def is_user_id(cls, user_id: str) -> bool:
        """It checks if the user_id is valid matrix user_id

        Parameters
        ----------
        user_id : str
            The user ID to check.

        Returns
        -------
            A boolean value.

        """
        return user_id.startswith("@")

    @classmethod
    def is_room_id(cls, room_id: str) -> bool:
        """It checks if the room_id is valid matrix room_id

        Parameters
        ----------
        room_id : str
            The room ID to check.

        Returns
        -------
            A boolean value.

        """
        return room_id.startswith("!")

    @classmethod
    def is_room_alias(cls, room_alias: str) -> bool:
        """It checks if the room_alias is valid matrix room_alias

        Parameters
        ----------
        room_alias : str
            The room alise to check.

        Returns
        -------
            A boolean value.

        """
        return room_alias.startswith("#")

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
            formatted_text = formatted_text.replace("<br>", "\n")
            formatted_text = formatted_text.replace("**", "")
            plain_text = BeautifulSoup(formatted_text, features="html.parser").text
            return plain_text
        else:
            return formatted_text
