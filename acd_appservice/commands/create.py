from mautrix.types import PowerLevelStateEventContent

from ..puppet import Puppet
from ..util import Util
from .handler import CommandArg, CommandEvent, command_handler

destination = CommandArg(
    name="destination",
    help_text="Method to distribution of new chats",
    is_required=False,
    example="`@user_id:foo.com`| `!foo:foo.com`",
)


bridge = CommandArg(
    name="bridge",
    help_text="Bridge bot that will be invited to the control room if you want it",
    is_required=False,
    example="`mautrix`| `instagram` | `gupshup`",
    sub_args=[destination],
)


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
    help_args=[bridge],
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

    puppet = None

    # We get the following puppet available in the bd
    next_puppet = await Puppet.get_next_puppet()
    invitees = [evt.sender.mxid]

    if not next_puppet:
        evt.reply("We have not been able to create the `acd[n]`")
        return

    try:
        bridge = evt.args_list[0]
    except IndexError:
        bridge = ""

    try:
        destination = evt.args_list[1]
    except IndexError:
        destination = ""

    try:
        # We create the puppet with the following pk
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
                invitees.append(destination)
            else:
                if Util.is_room_alias(destination) or Util.is_room_id(destination):
                    await evt.intent.bot.join_room(room_id_or_alias=destination)

            puppet.destination = destination

        if bridge:
            # Register the bridge the puppet belongs to
            bridge_bot = evt.config[f"bridges.{bridge}.mxid"]
            puppet.bridge = bridge
            invitees.append(bridge_bot)

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
