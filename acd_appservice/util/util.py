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
