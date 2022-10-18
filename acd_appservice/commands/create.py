from mautrix.types import PowerLevelStateEventContent

from ..puppet import Puppet
from ..util import Util
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    management_only=True,
    needs_admin=True,
    name="create",
    help_text=(
        "Create an acd*, if you send `bridge` then the bridgebot will be invited."
        "If you have already created a control room and you want this room to be used by the acd*, "
        "then you must first invite them so that they can join using this command. "
        "If you send `destination`, then the distribution of new chats related to this acd* "
        "will be done following this method. This field can be a room_id or a user_id."
    ),
    help_args="[_bridge_] [_destination_] [_control_room_id_]",
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

    bridge = ""
    destination = ""
    control_room_id = ""
    puppet = None

    if len(evt.args) >= 1:

        bridge = evt.args[0]
        bridge_bot = evt.config[f"bridges.{bridge}.mxid"]

        if len(evt.args) >= 2:
            destination = evt.args[1]  # Could be a user_id, room_id or a room_alias

        if len(evt.args) >= 3:
            control_room_id = evt.args[2]  # An existing room that you want to reuse

    # We get the following puppet available in the bd
    next_puppet = await Puppet.get_next_puppet()
    invitees = [evt.sender.mxid]

    if not next_puppet:
        evt.reply("We have not been able to create the `acd*`")
        return

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

        # If no control room has been sent, then we create a
        if not control_room_id:

            control_room_id = await puppet.intent.create_room(
                name=f"{evt.config[f'bridge.puppet_control_room.name']}({puppet.email or puppet.custom_mxid})",
                topic=f"{evt.config[f'bridge.puppet_control_room.topic']}",
                invitees=invitees,
            )

            await puppet.intent.set_power_levels(
                room_id=control_room_id, content=power_level_content
            )

        puppet.control_room_id = control_room_id

        # Now if we store the control room in the puppet.control_room_id
        await puppet.save()
        # If you want to set the initial state of the puppets, you can do it in this
        # function
        await puppet.sync_puppet_account()
    except Exception as e:
        evt.log.exception(e)

    return puppet
