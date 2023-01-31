# v0.2.6 (2023-01-31)
- Rename methods to obtain serialized memberships
- Modified members endpoint to return the status of all agents
- Added new queue action that adds previously created rooms
- Added method to obtain the room theme
- Added support for connecting to the Facebook bridge
- Added examples in the login and challenge documentation
- Changed queue command execution permission
- Respond to an error when the command fails
- Added new update_members endpoint
- Added displayname in the user membership response
- Refactoring for the use of portal and queue in some parts of the code
- Fixed errors when the agent leaves the queue
- Fixed when the room is created and menubot is not invited
- Fixed errors when guests are an empty string
- Fixed errors in the portal database query
- Fixed errors in the queue membership list
- Fixed errors in the queue command
- Fixed errors in the information and queue list endpoints

# v0.2.5 (2023-01-03)
- Added CRUD operations for queue command.
- Renamed Room class to MatrixRoom.
- Expanded command processor operations.
- Obtained version from Git.
- Fixed dates in agent operations.
- Endpoint to get agent pause state.
- Added room name in JSON response in members command.
- Endpoint to get user members.
- Fixed errors in members endpoint.
- Fixed bugs in puppet identifier resolution.

# v0.2.4.2 (2023-01-25)
- Changed the method for removing room_id
- Fixed the issue when creating the room and not inviting menubot.

# v0.2.4.1 (2022-12-13)
- Fixed mautrix python cache error

# v0.2.4 (2022-12-07)
- Command processor refactoring with new documentation structure.
- Added a member pause command.
- Adjustment in the database to add a description field to the queue table and use it in the queue command.
- Agent operations added, including login and logout.
- Added a command to create agent queues from the ACD.
- Sending unformatted messages to bridges that do not support formatted messages.
- Fixing errors in the creation command.
- Adding tests for the member and member pause commands.
- Change in date and time data type in the queue membership table.

# v0.2.3 (2022-11-15)
- Fixed a bug related to room control when distributing chat when the campaign room id is null.

# v0.2.2 (2022-11-03)
- Fixed an error related to transfer command, when the room_id of the campaign was not available to the main ACD.
- Corrected the get_bridges_status function to skip gupshup bridge status validation.
- Added an endpoint in the API for the ACD command.
- Improvements were made in the logout endpoint documentation.
- Refactored get_bridges_status, ProvisionBridge and created the logout endpoint.

# v0.2.0 (2022-10-18)
- Added endpoint to get the status of channels
- Fixed an error in the transfer_user function
- Added a "force" argument to the transfer_user function to force the transfer of user
- Added a new function to create commands and refactored the web module to have separate endpoints
- Added a script for the development team
- Changed the Gupshup service URL to the default installation URL of the bridge
- Removed the need to send an email when creating a puppet user
- Ignored the "dev" directory and removed it
- Added suggestions and fixed a config.py configuration file error related to the leave_or_kick parameter
- Parameterized the command to expel or leave a user.


# v0.1.9 (2022-09-15)
- The ACD main bot distributes chats in group rooms.
- Update of dependencies and removal of unused imports.
- Correction of a bug while registering the Gupshup application.
- Movement of offline menu to a better location.
- Change from httpclient session to puppet session.
- Refactoring of CommandEvent.
- Update of docker-compose and .gitignore.
- Removal of the bridge field in the room resolution request.
- Addition of the agent name in the transfer message.
- Added documentation for the create_user endpoint.
- Addition of a function where users do not get kicked out but leave on their own.

# v0.1.8 (2022-08-31)
- ➕ ADD FEATURE: You can now send messages through gupshup using this endpoint `/v1/gupshup/send_message`
- ➕ ADD FEATURE: You can now create lines with gupshup using this endpoint `/v1/gupshup/register`
- ➕ ADD FEATURE: This ACD supports gupshup bridge
- 🔃 CODE REFACTORING: Changes to endpoints
    - `/v1/whatsapp/send_message` -> `/v1/mautrix/send_message`
    - `/v1/whatsapp/link_phone` -> `/v1/mautrix/link_phone`
    - `/v1/whatsapp/ws_link_phone` -> `/v1/mautrix/ws_link_phone`
- 🔃 CODE REFACTORING: The pm command was modified to work alongside mautrix and gupshup

# v0.1.7 (2022-08-24)

- 🐛 BUG FIX: The join event was arriving before the invite, rooms were not initializing correctly
- 🐛 BUG FIX: puppet_password was updating on its own upon restarting the service
- ➖ REMOVAL: Duplicate code was removed
# v0.1.6 (2022-22-08)

- 🐛 BUG FIX: Bug related to joined_message
- ➕ ADD FEATURE: Now generate puppet password automatically

# v0.0.0 (2022-06-06)

Initial tagged release.
