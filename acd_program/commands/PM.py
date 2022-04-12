
from mautrix.bridge.commands import HelpSection, command_handler

from .typehint import CommandEvent

SECTION_MISC = HelpSection("Miscellaneous", 40, "")


@command_handler(
    needs_auth=False,
    management_only=False,
    help_section=SECTION_MISC,
    help_text="Envia PM a la sala del bridge para crear un chat nuevo",
    help_args="<_phone_>",
)
async def search(evt: CommandEvent) -> None:
    if len(evt.args) < 1:
        await evt.reply("**Usage:** `$cmdprefix+sp search <phone>`")
        return


    evt.log.debug(f"######### {evt.args}")
