import shortuuid

from acd_program.user import User


class Utils:
    """Clase con diferentes utilidades"""

    async def create_puppet_and_user(self, email: str) -> tuple:
        """Create a user and his puppet.

        Given a email creates a User and to that User creates a puppet

        Parameters
        ----------
        email
            User email

        Returns
        -------
        tuple
            (user, puppet)
        """
        user = await User.get_by_email(email)
        if not user:
            user_id = str(shortuuid.uuid())
            user = await User.get_by_mxid(user_id)
            user.email = email
        # Se crea un Puppet si no existe, si existe se retorna
        pupp = await user.get_puppet()
        return user, pupp
