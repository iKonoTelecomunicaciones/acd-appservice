from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, NamedTuple, Type

from mautrix.types import MessageEventContent, RoomID
from mautrix.util.logging import TraceLogger

from ..commands.typehint import ArgParser, CommandArg, CommandEvent
from ..config import Config
from ..user import User

command_handlers: dict[str, CommandHandler] = {}
command_aliases: dict[str, CommandHandler] = {}

from mautrix.appservice import IntentAPI

HelpCacheKey = NamedTuple(
    "HelpCacheKey", is_management=bool, is_portal=bool, is_admin=bool, is_logged_in=bool
)

CommandHandlerFunc = Callable[[CommandEvent], Awaitable[Any]]

log: TraceLogger = logging.getLogger("mau.commands")


class CommandHandler:

    management_only: bool
    needs_admin: bool
    name: str
    _help_text: str
    _help_args: List[CommandArg] = []
    _help_sub_args: List[CommandArg] = []

    def __init__(
        self,
        handler: CommandHandlerFunc,
        management_only: bool,
        name: str,
        help_text: str,
        help_args: List[CommandArg],
        needs_admin: bool,
        help_sub_args: List[CommandArg] | None = None,
    ) -> None:
        self.management_only = management_only
        self.needs_admin = needs_admin
        self._handler = handler
        self.name = name
        self._help_text = help_text
        self._help_args = help_args
        self._help_sub_args = help_sub_args

    async def get_permission_error(self, evt: CommandEvent) -> str | None:
        """Returns the reason why the command could not be issued.

        Args:
            evt: The event for which to get the error information.

        Returns:
            A string describing the error or None if there was no error.
        """
        if self.management_only and not evt.is_management:
            return (
                f"`{evt.command}` is a restricted command: "
                "you may only run it in management rooms."
            )
        elif self.needs_admin and not evt.sender.is_admin:
            return "That command is limited to ACD administrators."
        return None

    def has_permission(self, key: HelpCacheKey) -> bool:
        """Checks the permission for this command with the given status.

        Args:
            key: The help cache key. See meth:`CommandEvent.get_cache_key`.

        Returns:
            True if a user with the given state is allowed to issue the
            command.
        """
        return (not self.management_only or key.is_management) and (
            not self.needs_admin or key.is_admin
        )

    async def __call__(self, evt: CommandEvent) -> Any:
        """Executes the command if evt was issued with proper rights.

        Args:
            evt: The CommandEvent for which to check permissions.

        Returns:
            The result of the command or the error message function.
        """

        error = await self.get_permission_error(evt)

        if error is not None:
            evt.log.warning(error)
            return await evt.reply(error)
        return await self._handler(evt)

    @property
    def help(self) -> str:
        """Returns the help text to this command."""
        text = ""

        if isinstance(self._help_args, list):
            for cmd_arg in self._help_args:
                if isinstance(cmd_arg, CommandArg):
                    text += f"{cmd_arg._name} {'[...]' if self._help_sub_args else ''}"

        text += 2 * "\n"

        if self._help_text:
            text += f"\t{self._help_text}\n"

        return f"\n{text}\n"

    @property
    def detail(self) -> str:
        text = f"#### Command: {self.name}\n"
        text += f"{self._help_text}\n\n"

        text += f"##### MainArgs\n\n"

        for cmd_arg in self._help_args:
            text += f"- {cmd_arg.detail}\n"

        text += f"##### SubArgs\n\n"

        for cmd_arg in self._help_sub_args:
            text += f"- {cmd_arg.detail}\n"

        return text


class CommandProcessor:
    """Handles the raw commands issued by a user to the Matrix bot."""

    log: TraceLogger = logging.getLogger("mau.commands")
    event_class: Type[CommandEvent]
    _ref_no: int

    def __init__(self, config: Config, event_class: Type[CommandEvent] = CommandEvent) -> None:
        self.config = config
        self.command_prefix = self.config["bridge.command_prefix"]
        self.event_class = event_class

    @staticmethod
    def _run_handler(
        handler: Callable[[CommandEvent], Awaitable[Any]], evt: CommandEvent
    ) -> Awaitable[Any]:
        try:
            return handler(evt)
        except TypeError:
            return

    async def handle(
        self,
        sender: User,
        command: str,
        args_list: list[str],
        is_management: bool,
        content: MessageEventContent = None,
        intent: IntentAPI = None,
        room_id: RoomID = "",
    ) -> Dict:
        """It takes the command, checks if it's a command or an alias,
        and then runs the handler for that command

        Parameters
        ----------
        sender : User
            The user who sent the command.
        command : str
            The command that was sent to the bot.
        args : list[str]
            list[str]
        is_management : bool
            If the command was sent in an ACD management room
        intent : IntentAPI
            The intent that sent the command.
        room_id : RoomID
            The room ID of the room the command was sent in.

        Returns
        -------
            The return value of the handler.

        """

        evt = self.event_class(
            room_id=room_id,
            config=self.config,
            intent=intent,
            sender=sender,
            command=command,
            args_list=args_list,
            text=content.body.strip() if content else "",
            is_management=is_management,
        )

        command = command.lower()

        self.log.debug(
            f"Incoming command from {room_id if room_id else None} :: {command} {args_list}"
        )

        handler = command_handlers.get(command, command_aliases.get(command))

        if len(args_list) > 0 and args_list[0] == "help":
            await evt.reply(handler.detail)
            return

        if handler._help_args:
            evt.args = self.parse_arguments(handler=handler, args=args_list)

        if handler is None:
            handler = command_handlers["unknown_command"]

        try:
            # Trying to delete the log from the result.
            result = await self._run_handler(handler, evt)

            # If a dict with a `log` field is returned, it will be removed,
            # this is done to connect the response of the commands with the provisioning API.
            if result:
                try:
                    del result["log"]
                except KeyError:
                    pass
            return result

        except Exception:
            detail = (
                "Unhandled error while handling command "
                f"{evt.command} {' '.join(args_list)} from {sender.mxid})"
            )
            self.log.exception(detail)
            return {"error": detail}

    def parse_arguments(self, handler: CommandHandler, args: List) -> ArgParser:
        """It takes the arguments from the command and puts them into an ArgParser object

        Parameters
        ----------
        handler : CommandHandler
            The command handler that is being called.
        args : List
            List - The list of arguments that the user has passed in.

        Returns
        -------
            The ArgParser object is being returned.

        """

        arg_parser = ArgParser()
        aux_args = handler._help_args + handler._help_sub_args

        for index in range(0, len(aux_args)):
            try:
                arg_parser.__setattr__(aux_args[index].name, args[index])
            except IndexError:
                if aux_args[index].default:
                    arg_parser.__setattr__(aux_args[index].name, aux_args[index].default)
                else:
                    arg_parser.__setattr__(aux_args[index].name, None)

        return arg_parser


def command_handler(
    _func: CommandHandlerFunc | None = None,
    *,
    management_only: bool = False,
    name: str | None = None,
    help_text: str = "",
    help_args: List[CommandArg] = [],
    help_sub_args: List[CommandArg] = [],
    needs_admin: bool = False,
    _handler_class: Type[CommandHandler] = CommandHandler,
) -> Callable[[CommandHandlerFunc], CommandHandler]:
    """It takes a function and returns a decorator that takes a function and returns a class

    Parameters
    ----------
    _func : CommandHandlerFunc | None
        This is the function that will be decorated.
    management_only : bool, optional
        If True, the command will only be available in the management channel.
    name : str | None
        The name of the command. If not provided, it will be the name of the function.
    help_text : str
        The help text that will be displayed when the user types !help <command>
    help_args : str
        The arguments that the command takes.
    needs_admin : bool, optional
        If True, the command can only be run by an admin.
    _handler_class : Type[CommandHandler]
        This is the class that will be used to create the handler.

    Returns
    -------
        A decorator function that takes a function as an argument and returns a CommandHandler object.

    """

    def decorator(func: CommandHandlerFunc) -> CommandHandler:
        actual_name = name or func.__name__
        handler = _handler_class(
            func,
            management_only=management_only,
            name=actual_name,
            help_text=help_text,
            help_args=help_args,
            help_sub_args=help_sub_args,
            needs_admin=needs_admin,
        )
        command_handlers[handler.name] = handler
        return handler

    return decorator if _func is None else decorator(_func)
