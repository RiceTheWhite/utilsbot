from typing import Optional

import discord
from discord import app_commands
import os
from jsonHandler import JsonHandler

MY_GUILD = discord.Object(id=1382525385803305030)  # replace with your guild id


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

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')


jsonHandler = JsonHandler(filename="save.json")
reaction_role_map = jsonHandler.map

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
    jsonHandler.save()

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

    mapping = jsonHandler.map.get(message_id_int)
    if not mapping or emoji not in mapping:
        await interaction.response.send_message("❌ No such reaction-role mapping found.", ephemeral=True)
        return

    # Remove mapping
    del jsonHandler.map[message_id_int][emoji]
    if not jsonHandler.map[message_id_int]:  # clean up empty dicts
        del jsonHandler.map[message_id_int]

    jsonHandler.save()

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

client.run(os.environ["TOKEN"])
