from argparse import ArgumentParser, Namespace

from mautrix.types import PowerLevelStateEventContent

from ..puppet import Puppet
from ..user import User
from ..util import Util
from .handler import CommandArg, CommandEvent, command_handler

destination_arg = CommandArg(
    name="--destination or -d",
    help_text="Method to distribution of new chats",
    is_required=True,
    example="`@user_id:foo.com`| `!foo:foo.com`",
)


bridge_arg = CommandArg(
    name="--bridge or -b",
    help_text="Bridge bot that will be invited to the control room if you want it",
    is_required=False,
    example="`mautrix`| `instagram` | `gupshup`",
)


email_arg = CommandArg(
    name="--email or -e",
    help_text="Email to assign to the puppet",
    is_required=False,
    example="`user_id@foo.com`| `user_id@gmail.com`",
)


def args_parser():
    parser = ArgumentParser(description="CREATE", exit_on_error=False)

    parser.add_argument("--destination", "-d", dest="destination", type=str)
    parser.add_argument("--bridge", "-b", dest="bridge", type=str, default="")
    parser.add_argument("--email", "-e", dest="email", type=str, default="")

    return parser


@command_handler(
    management_only=True,
    needs_admin=True,
    name="create",
    help_text=(
        "Create an acd[n], if you send `bridge` then the bridgebot will be invited."
        "If you have already created a control room and you want this room to be used by the acd[n], "
        "then you must first invite them so that they can join using this command. "
        "If you send `destination`, then the distribution of new chats related to this acd[n] "
        "will be done following this method. This field can be a room_id or a user_id."
    ),
    help_args=[bridge_arg, destination_arg, email_arg],
    args_parser=args_parser(),
)
async def create(evt: CommandEvent) -> Puppet:
    """We create a puppet, we create a control room, we invite the puppet,
    the bridge and the users that we want to invite

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        The puppet object

    """

    # We get the following puppet available in the bd
    next_puppet = await Puppet.get_next_puppet()
    invitees = [evt.sender.mxid]

    if not next_puppet:
        await evt.reply("We have not been able to create the `acd[n]`")
        return

    args: Namespace = evt.cmd_args

    bridge = args.bridge
    destination = args.destination
    email = args.email

    try:
        # We create the puppet with the next puppet id
        puppet: Puppet = await Puppet.get_by_pk(pk=next_puppet)

        # Initialise the intent of this puppet
        puppet.intent = puppet._fresh_intent()
        await puppet.save()
        # Save the puppet for use in other parts of the code.
        # Synchronise the puppet's rooms, if it already existed in Matrix
        # without us realising it
        await puppet.sync_joined_rooms_in_db()

        if destination:
            if Util.is_user_id(destination):
                user: User = await User.get_by_mxid(destination, create=False)
                if user and user.is_menubot:
                    invitees.append(destination)

            puppet.destination = destination

        if bridge:
            # Register the bridge the puppet belongs to
            bridge_bot = evt.config[f"bridges.{bridge}.mxid"]
            puppet.bridge = bridge
            invitees.append(bridge_bot)

        if email:
            # Register the email of the puppet
            puppet.email = email

        power_level_content = PowerLevelStateEventContent(
            users={
                puppet.mxid: 100,
            }
        )

        for user_id in evt.config["bridge.puppet_control_room.invitees"]:
            if user_id not in invitees:
                invitees.append(user_id)

            power_level_content.users[user_id] = 100

        await evt.reply(f"The users {invitees} will be invited")

        control_room_id = await puppet.intent.create_room(
            name=f"{evt.config[f'bridge.puppet_control_room.name']}({puppet.email or puppet.custom_mxid})",
            topic=f"{evt.config[f'bridge.puppet_control_room.topic']}",
        )

        puppet.control_room_id = control_room_id
        # Now if we store the control room in the puppet.control_room_id
        await puppet.save()

        for invitee in invitees:
            await puppet.intent.invite_user(room_id=control_room_id, user_id=invitee)

        await puppet.intent.set_power_levels(room_id=control_room_id, content=power_level_content)

        # If you want to set the initial state of the puppets, you can do it in this
        # function
        await puppet.sync_puppet_account()
    except Exception as e:
        evt.log.exception(e)

    return puppet
