from __future__ import annotations

import logging
from argparse import ArgumentParser, Namespace
from typing import Any, Awaitable, Callable, Dict, List, NamedTuple, Type

from attr import dataclass
from markdown import markdown
from mautrix.appservice import IntentAPI
from mautrix.types import Format, MessageEventContent, MessageType, RoomID, TextMessageEventContent
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..user import User

command_handlers: dict[str, CommandHandler] = {}
command_aliases: dict[str, CommandHandler] = {}


HelpCacheKey = NamedTuple(
    "HelpCacheKey", is_management=bool, is_portal=bool, is_admin=bool, is_logged_in=bool
)


class CommandEvent:
    log: TraceLogger = logging.getLogger("acd.cmd")
    processor: CommandProcessor
    sender: "User"

    def __init__(
        self,
        processor: CommandProcessor,
        sender: User,
        config: Config,
        command: str,
        is_management: bool,
        intent: IntentAPI = None,
        room_id: RoomID = None,
        text: str = None,
        cmd_args: Namespace = None,
    ):
        self.command = command
        self.processor = processor
        self.log = self.log.getChild(self.command)
        self.intent = intent
        self.config = config
        self.command_prefix = config["bridge.command_prefix"]
        self.sender = sender
        self.room_id = room_id
        self.is_management = is_management
        self.text = text
        self.cmd_args = cmd_args

    async def reply(self, text: str) -> None:
        """It sends a message to the room that the event was received from

        Parameters
        ----------
        text : str
            The text to send.

        """
        if not text or not self.room_id:
            return

        try:
            # Sending a message to the room that the event was received from.
            html = markdown(text)
            content = TextMessageEventContent(
                msgtype=MessageType.NOTICE, body=text, format=Format.HTML, formatted_body=html
            )

            await self.intent.send_message(
                room_id=self.room_id,
                content=content,
            )
        except Exception as e:
            self.log.exception(e)


@dataclass
class CommandArg:
    name: str
    help_text: str
    example: str
    is_required: bool = False
    sub_args: List[List[CommandArg] | CommandArg] = []

    @property
    def _name(self) -> str:
        return f"<_{self.name}_>" if self.is_required else f"[_{self.name}_]"

    @property
    def detail(self) -> str:
        help_text = f"**{self._name}**: {self.help_text} -> **example**: {self.example}\n\n"

        if not self.sub_args:
            return help_text

        help_text += 2 * "\n"
        help_text += "##### SubArgs"

        counter = 1

        for sub_arg in self.sub_args:
            help_text += f"\n\n __**Argument order: {counter}**__"
            if not isinstance(sub_arg, list):
                help_text += f"\n\n- {sub_arg.detail}"
            else:
                help_text += f"\n\n- {'- '.join([arg.detail for arg in sub_arg])}"
                help_text += "---"

            counter += 1

        return help_text


CommandHandlerFunc = Callable[[CommandEvent], Awaitable[Any]]


class CommandHandler:
    management_only: bool
    needs_admin: bool
    name: str
    _help_text: str
    _help_args: List[CommandArg] = []

    def __init__(
        self,
        handler: CommandHandlerFunc,
        management_only: bool,
        name: str,
        help_text: str,
        help_args: List[CommandArg],
        needs_admin: bool,
        args_parser: ArgumentParser,
    ) -> None:
        self.management_only = management_only
        self.needs_admin = needs_admin
        self._handler = handler
        self.name = name
        self._help_text = help_text
        self._help_args = help_args
        self._args_parser = args_parser

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
            await evt.reply(error)
            return {"data": {"error": error}, "status": 500}
        return await self._handler(evt)

    @property
    def help(self) -> str:
        """Returns the help text to this command."""
        text = ""

        if isinstance(self._help_args, list):
            for cmd_arg in self._help_args:
                if isinstance(cmd_arg, CommandArg):
                    text += f"{cmd_arg._name} {'[...]' if cmd_arg.sub_args else ''}"

        text += 2 * "\n"

        if self._help_text:
            text += f"\t{self._help_text}\n"

        return f"\n{text}\n"

    @property
    def detail(self) -> str:
        text = f"#### Command: {self.name}\n"
        text += f"{self._help_text}\n\n"

        if self._help_args:
            text += f"##### MainArgs\n\n"

            for cmd_arg in self._help_args:
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
        """It handles the incoming command.

        Parameters
        ----------
        sender : User
            User - The user who sent the command
        command : str
            The command that was sent.
        args_list : list[str]
            list[str]
        is_management : bool
            Whether the command was sent by a management user.
        content : MessageEventContent
            The content of the message event.
        intent : IntentAPI
            IntentAPI = None,
        room_id : RoomID
            The room ID of the room the command was sent in.

        Returns
        -------
            The return value is a dictionary with two keys: data and status.

        """

        command = command.lower()

        self.log.debug(
            f"Incoming command from {room_id if room_id else None} :: {command} {args_list}"
        )

        handler = command_handlers.get(command, command_aliases.get(command))

        if handler is None:
            handler = command_handlers["unknown_command"]

        command_arguments = handler._args_parser.parse_args(args_list)

        evt = self.event_class(
            processor=self,
            room_id=room_id,
            config=self.config,
            intent=intent,
            sender=sender,
            command=command,
            cmd_args=command_arguments,
            text=content.body.strip() if content else "",
            is_management=is_management,
        )

        _args: Dict[str, CommandArg] = {}

        for arg in handler._help_args:
            if arg.sub_args:
                for sub_arg in arg.sub_args:
                    if not isinstance(sub_arg, list):
                        _args[sub_arg.name] = sub_arg
                    else:
                        for aux_arg in sub_arg:
                            _args[aux_arg.name] = aux_arg

            _args[arg.name] = arg

        if len(args_list) == 1 and args_list[0] == "help":
            return await evt.reply(handler.detail)

        elif evt.command == "help":
            return await self._run_handler(handler, evt)

        elif len(args_list) > 1 and args_list[-1] == "help":
            try:
                return await evt.reply(_args[args_list[-2]].detail)
            except KeyError:
                return await evt.reply(
                    f"**{args_list[-2]}** is not a parameter that has help text"
                )

        try:
            # Trying to delete the log from the result.
            return await self._run_handler(handler, evt)

        except Exception:
            detail = (
                "Unhandled error while handling command "
                f"{evt.command} {' '.join([str(arg) for arg in args_list])} from {sender.mxid})"
            )
            self.log.exception(detail)
            return {"data": {"error": detail}, "status": 500}


def command_handler(
    _func: CommandHandlerFunc | None = None,
    *,
    management_only: bool = False,
    name: str | None = None,
    help_text: str = "",
    help_args: Dict[CommandArg] = {},
    needs_admin: bool = False,
    args_parser: ArgumentParser = None,
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
    args_parser: ArgumentParser
        Command argument parser
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
            needs_admin=needs_admin,
            args_parser=args_parser,
        )
        command_handlers[handler.name] = handler
        return handler

    return decorator if _func is None else decorator(_func)
