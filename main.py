from typing import Optional

import discord
from discord import app_commands
import os
from jsonHandler import JsonHandler
from dotenv import load_dotenv, dotenv_values
load_dotenv()

MY_GUILD = discord.Object(id=1071479459498164459)  # replace with your guild id


class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)


intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True
client = MyClient(intents=intents)

def has_manage_roles():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.manage_roles
    return app_commands.check(predicate)

def has_ban_perms():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.ban_members
    return app_commands.check(predicate)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')


reactionMapHandler = JsonHandler(filename="save.json")
reaction_role_map = reactionMapHandler.map




# @client.event
# async def on_message(message):
#     if message.author == client.user:
#         return
#
#     if message.content.startswith('im '):
#         content = message.content
#         await message.channel.send(f'hi {content[3:]} im bot')


@client.tree.command(name="add_reaction_role", description="Add a reaction-role mapping from a message.")
@has_manage_roles()
async def add_reaction_role(
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role
):
    """Assign a role when reacting to a specific message with a given emoji."""

    try:
        message_id = int(message_id)
    except ValueError:
        await interaction.response.send_message("Invalid message ID.", ephemeral=True)
        return

    if message_id not in reaction_role_map:
        reaction_role_map[message_id] = {}

    reaction_role_map[message_id][emoji] = role.id
    reactionMapHandler.save()

    # Try to react to the message
    try:
        channel = interaction.channel
        message = await channel.fetch_message(message_id)
        await message.add_reaction(emoji)
    except discord.NotFound:
        await interaction.response.send_message("Message not found.", ephemeral=True)
        return
    except discord.HTTPException:
        await interaction.response.send_message("Failed to react to the message.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"✅ Reaction role set: {emoji} → {role.name} on message {message_id}",
        ephemeral=True
    )


@client.tree.command(name="remove_reaction_role", description="Remove a reaction-role mapping from a message.")
@has_manage_roles()
async def remove_reaction_role(
    interaction: discord.Interaction,
    message_id: str,
    emoji: str
):
    try:
        message_id_int = int(message_id)
    except ValueError:
        await interaction.response.send_message("Invalid message ID.", ephemeral=True)
        return

    mapping = reaction_role_map.get(message_id_int)
    if not mapping or emoji not in mapping:
        await interaction.response.send_message("❌ No such reaction-role mapping found.", ephemeral=True)
        return

    # Remove mapping
    del reaction_role_map[message_id_int][emoji]
    if not reaction_role_map[message_id_int]:  # clean up empty dicts
        del reaction_role_map[message_id_int]

    reactionMapHandler.save()

    # Try to remove the reaction
    try:
        message = await interaction.channel.fetch_message(message_id_int)
        await message.clear_reaction(emoji)
    except discord.HTTPException:
        await interaction.response.send_message("Mapping removed, but failed to remove the emoji reaction.", ephemeral=True)
        return

    await interaction.response.send_message(f"✅ Reaction-role mapping for {emoji} removed from message {message_id}.", ephemeral=True)



@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id in reaction_role_map:
        guild = client.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        emoji = str(payload.emoji)

        role_id = reaction_role_map[payload.message_id].get(emoji)
        if role_id and member and member != client.user:
            role = guild.get_role(role_id)
            if role:
                await member.add_roles(role)

@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id in reaction_role_map:
        guild = client.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        emoji = str(payload.emoji)

        role_id = reaction_role_map[payload.message_id].get(emoji)
        if role_id and member and member != client.user:
            role = guild.get_role(role_id)
            if role:
                await member.remove_roles(role)

@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command, or something went wrogn tell me asap...",
            ephemeral=True
        )
    else:
        raise error  # Re-raise unhandled exceptions


@client.tree.command(name="warn", description="Warns a user.")
@has_ban_perms()
async def warn(
    interaction: discord.Interaction,
    user: discord.User,
    message: str
):
    try:
        await user.send(f"⚠️ You have been warned in **{interaction.guild.name}** for: {message}")
    except discord.Forbidden:
        print("❌ Could not DM the user. They may have DMs closed.")

    await interaction.response.send_message(f"✅ {user.mention} has been warned for: `{message}`", ephemeral=False)


@client.tree.command(name="mute", description="Mutes a user by assigning a 'Muted' role.")
@has_ban_perms()
async def mute(
    interaction: discord.Interaction,
    user: discord.Member,  # note: must be Member to modify roles
    message: str
):
    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not muted_role:
        await interaction.response.send_message("❌ 'Muted' role not found. Please create one first.", ephemeral=True)
        return

    try:
        await user.add_roles(muted_role, reason=message)
        await user.send(f"🔇 You have been muted in **{interaction.guild.name}** for: {message}")
        await interaction.response.send_message(f"✅ {user.mention} has been muted for: `{message}`", ephemeral=False)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I do not have permission to mute this user.", ephemeral=True)


@client.tree.command(name="ban", description="Bans a user.")
@has_ban_perms()
async def ban(
    interaction: discord.Interaction,
    user: discord.User,
    message: str
):
    try:
        await interaction.guild.ban(user, reason=message)
        await interaction.response.send_message(f"✅ {user.mention} has been banned for: `{message}`", ephemeral=False)

        try:
            await user.send(f"⛔ You have been banned from **{interaction.guild.name}** for: {message}")
        except discord.Forbidden:
            pass  # user may have DMs closed
    except discord.Forbidden:
        await interaction.response.send_message("❌ I do not have permission to ban this user.", ephemeral=True)


client.run(os.environ["TOKEN"])
