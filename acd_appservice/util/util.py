from asyncio import AbstractEventLoop
from re import match

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

    async def schedule_task(self, loop: AbstractEventLoop, future: float, task: function):
        loop.call_later(future, task)
