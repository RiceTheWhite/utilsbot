from typing import Optional

import discord
from discord import app_commands
import os
from jsonHandler import JsonHandler
from dotenv import load_dotenv, dotenv_values
import yt_dlp
import tempfile

load_dotenv()

MY_GUILD = discord.Object(id=os.environ["GUILD_ID"])  # replace with your guild id


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
    await client.tree.sync()
    client.add_view(TicketView())  # persistent "open ticket" button
    client.add_view(CloseTicketView())  # persistent "close ticket" button
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')


# ---------------------------
# REACTION ROLES
# ---------------------------

reactionMapHandler = JsonHandler(filename="save.json")
reaction_role_map = reactionMapHandler.map


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
        await interaction.response.send_message("Mapping removed, but failed to remove the emoji reaction.",
                                                ephemeral=True)
        return

    await interaction.response.send_message(f"✅ Reaction-role mapping for {emoji} removed from message {message_id}.",
                                            ephemeral=True)


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


# ---------------------------
# WELCOMER
# ---------------------------

welcomeHandler = JsonHandler("welcome.json")
welcome_config = welcomeHandler.map


class WelcomeMessageModal(discord.ui.Modal, title="Set Welcome Message"):
    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

        self.message_input = discord.ui.TextInput(
            label="Welcome Message",
            style=discord.TextStyle.paragraph,
            placeholder="Use {user} to mention the new member.",
            required=True,
            max_length=1000
        )
        self.color_input = discord.ui.TextInput(
            label="Embed Color (hex, e.g. #00ffcc)",
            style=discord.TextStyle.short,
            required=False,
            placeholder="#00ffcc"
        )
        self.gif_input = discord.ui.TextInput(
            label="GIF/Image URL (optional)",
            style=discord.TextStyle.short,
            required=False,
            placeholder="https://example.com/image.gif"
        )

        self.add_item(self.message_input)
        self.add_item(self.color_input)
        self.add_item(self.gif_input)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        # Parse color
        color_hex = self.color_input.value.strip() or "#00ffff"
        try:
            color = discord.Color(int(color_hex.strip("#"), 16))
        except ValueError:
            await interaction.response.send_message("❌ Invalid color hex. Use format like #00ffcc.", ephemeral=True)
            return

        # Basic GIF URL validation
        gif_url = self.gif_input.value.strip()
        if gif_url and not (gif_url.startswith("http") and any(
                gif_url.endswith(ext) for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp"])):
            await interaction.response.send_message("❌ Invalid image URL.", ephemeral=True)
            return

        message = self.message_input.value

        # Save config
        welcome_config[guild_id] = {
            "channel_id": self.channel.id,
            "message": message,
            "color": color.value,
            "gif_url": gif_url
        }
        welcomeHandler.save()

        # Build and send embed
        preview = message.replace("{user}", interaction.user.mention)
        embed = discord.Embed(description=preview, color=color)
        if gif_url:
            embed.set_image(url=gif_url)

        try:
            await self.channel.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Welcome embed configured for {self.channel.mention}.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I couldn't send the embed in that channel. Check my permissions.", ephemeral=True
            )


@client.tree.command(name="welcome", description="Set up the welcome message with embed.")
@has_ban_perms()
async def welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.send_modal(WelcomeMessageModal(channel))


@client.event
async def on_member_join(member: discord.Member):
    guild_id = str(member.guild.id)
    config = welcome_config.get(guild_id)
    if not config:
        return

    channel = member.guild.get_channel(config["channel_id"])
    if not channel:
        return

    color = discord.Color(config.get("color", 0x00FFFF))
    message = config.get("message", "Welcome {user}!").replace("{user}", member.mention)
    gif_url = config.get("gif_url")

    embed = discord.Embed(description=message, color=color)
    if gif_url:
        embed.set_image(url=gif_url)

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


# ---------------------------
# MUSIC
# ---------------------------

audio_state = {}


# Join command
@client.tree.command(name="join", description="Bot joins your voice channel.")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ You must be in a voice channel.", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    await channel.connect()
    await interaction.response.send_message(f"✅ Joined {channel.name}", ephemeral=True)


# Play command
@client.tree.command(name="play", description="Stream audio from a YouTube or Spotify link.")
@app_commands.describe(url="YouTube or Spotify URL")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True, ephemeral=False)

    voice = interaction.guild.voice_client
    if not voice:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ You must be in a voice channel.", ephemeral=True)
            return
        voice = await interaction.user.voice.channel.connect()

    ytdlp_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',  # IPv6 issues workaround
    }

    with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
            title = info.get('title', 'Unknown Title')
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to extract audio: {e}", ephemeral=True)
            return

    # Stream via FFmpeg
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }

    source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
    voice.play(source, after=lambda e: print(f"Finished playing: {e}"))

    await interaction.followup.send(f"🎧 Now streaming: **{title}**", ephemeral=False)


# Stop command
@client.tree.command(name="stop", description="Stop audio and leave voice.")
async def stop(interaction: discord.Interaction):
    voice = interaction.guild.voice_client
    if not voice:
        await interaction.response.send_message("❌ I'm not connected.", ephemeral=True)
        return

    # Stop playback
    voice.stop()
    await voice.disconnect()

    # Clean up
    filepath = audio_state.pop(interaction.guild.id, None)
    if filepath and os.path.exists(filepath):
        os.remove(filepath)

    await interaction.response.send_message("⏹️ Stopped and disconnected.", ephemeral=True)


# ---------------------------
# TICKETS
# ---------------------------

class TicketModal(discord.ui.Modal, title="Create Ticket Embed"):
    embed_description = discord.ui.TextInput(label="Embed Description", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            description=self.embed_description.value,
            color=discord.Color(int("#D5B9BA".strip("#"), 16))
        )
        view = TicketView()
        await interaction.response.send_message("✅ Ticket message created:", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)


class CloseWithReasonModal(discord.ui.Modal, title="Close Ticket with Reason"):
    reason = discord.ui.TextInput(
        label="Reason for closing the ticket",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=400
    )

    async def on_submit(self, interaction: discord.Interaction):
        await archive_ticket(interaction, reason=self.reason.value)


# View shown in the ticket channel
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="close", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await archive_ticket(interaction, reason="Closed by moderator")

    @discord.ui.button(label="close with reason", style=discord.ButtonStyle.gray, custom_id="close_ticket_reason")
    async def close_ticket_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CloseWithReasonModal())

    @discord.ui.button(label="claim", style=discord.ButtonStyle.blurple, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
            return

        await interaction.channel.edit(name=f"{interaction.channel.name}-claimed")
        await interaction.channel.send(f"🔒 Ticket claimed by {interaction.user.mention}")

        await interaction.response.send_message("You have claimed this ticket.", ephemeral=True)


# View shown in the main ticket embed
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="open ticket", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower().replace(' ', '-')}")
        if existing:
            await interaction.response.send_message("❌ You already have a ticket open!", ephemeral=True)
            return

        # Permissions setup
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        mod_roles = [role for role in guild.roles if role.permissions.ban_members]
        for role in mod_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name}".lower(),
            overwrites=overwrites,
            reason="New support ticket"
        )

        embed = discord.Embed(
            description=
            "────˚₊‧꒰ა ୨ৎ ໒꒱ ‧₊˚────\n"
            "\n"
            f"thanks for opening a ticket with us, {user.mention}! please give us your intro and a cupid will be with you shortly!\n"
            "\n"
            "────˚₊‧꒰ა ୨ৎ ໒꒱ ‧₊˚────",
            color=discord.Color(int("#D5B9BA".strip("#"), 16))
        )
        embed.set_footer(text=f"User ID: {user.id}")

        await ticket_channel.send(content=f"{user.mention}", embed=embed, view=CloseTicketView())

        await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)


@client.tree.command(name="create_ticket_message", description="Create a ticket embed with a button.")
@has_ban_perms()
async def create_ticket_message(interaction: discord.Interaction):
    await interaction.response.send_modal(TicketModal())


@client.tree.command(name="close_ticket", description="Close the current ticket channel.")
async def close_ticket_cmd(interaction: discord.Interaction):
    await close_ticket(interaction)


async def close_ticket(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return

    await interaction.response.send_message("🗑️ Closing this ticket...", ephemeral=True)
    await interaction.channel.delete(reason="Ticket closed")


async def archive_ticket(interaction: discord.Interaction, reason: str):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return

    overwrites = interaction.channel.overwrites
    # Update permissions to make the channel read-only for the user
    ticket_owner = None
    for target, perms in overwrites.items():
        if isinstance(target, discord.Member) and perms.view_channel and not target.bot:
            ticket_owner = target
            break

    if ticket_owner:
        overwrites[ticket_owner] = discord.PermissionOverwrite(view_channel=True, send_messages=False)

    await interaction.channel.edit(
        name=f"{interaction.channel.name}-archived",
        overwrites=overwrites,
        reason=reason
    )

    await interaction.channel.send(f"🗃️ This ticket has been archived.\n**Reason**: {reason}")
    await interaction.response.send_message("✅ Ticket archived.", ephemeral=True)


# ---------------------------
# SAY
# ---------------------------

@client.tree.command(name="say", description="make tamako say sum")
@has_ban_perms()
async def say(interaction: discord.Interaction):
    await interaction.response.send_modal(SayModal())


class SayModal(discord.ui.Modal, title="make tamako say sum"):
    message = discord.ui.TextInput(
        label="Message",
        placeholder="What should Tamako say?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    embed_color = discord.ui.TextInput(
        label="Embed Color (Hex, optional)",
        placeholder="#5865F2 or leave blank",
        required=False
    )

    gif_link = discord.ui.TextInput(
        label="GIF/Image URL (optional)",
        placeholder="https://media.giphy.com/media/abc123.gif",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Default color: #D5B9BA
        try:
            color = int(self.embed_color.value.lstrip('#'), 16) if self.embed_color.value else 0xD5B9BA
        except ValueError:
            await interaction.response.send_message("❌ Invalid hex color code.", ephemeral=True)
            return

        embed = discord.Embed(
            description=self.message.value,
            color=color
        )

        if self.gif_link.value:
            embed.set_image(url=self.gif_link.value)

        await interaction.response.send_message(embed=embed)


# ---------------------------
# RUN
# ---------------------------

client.run(os.environ["TOKEN"])
