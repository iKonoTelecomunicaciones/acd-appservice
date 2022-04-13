
from mautrix.bridge.commands import HelpSection, command_handler

from .typehint import CommandEvent

SECTION_GENERAL = HelpSection("General", 0, "")


@command_handler(
    needs_auth=False,
    management_only=False,
    help_section=SECTION_GENERAL,
    help_text="Envia PM a la sala del bridge para crear un chat nuevo",
    help_args="<_phone_>",
)
async def pm(evt: CommandEvent) -> None:
    if len(evt.args) < 1:
        await evt.reply("**Usage:** `$cmdprefix+sp search <phone>`")
        return


    evt.log.debug(f"######### {evt.args}")
