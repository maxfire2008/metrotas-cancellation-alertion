import datetime
import os
import time
import traceback
import discord
import discord.ext.tasks
import discord.ext.commands
import sys
import asyncio
import DatabaseController
import discord.app_commands

database_controller = DatabaseController("sqlite://database.db")

TEST_GUILD = discord.Object(1150694755618009168)


class SubscribeClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)

        self.prompt_creator_schedule_lock = asyncio.Lock()
        self.send_alerts_lock = asyncio.Lock()

        self.tree = discord.app_commands.CommandTree(self)

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        self.prompt_creator_schedule.start()
        self.send_alerts.start()

    async def setup_hook(self) -> None:
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)

    @discord.ext.tasks.loop(seconds=15)
    async def prompt_creator_schedule(self):
        content = (
            "Welcome to the Metro Cancellations Bot! This bot will send you a "
            + "DM or a message in a channel when your bus is cancelled. To get "
            + "started, click the button below to create an alert.\n\n"
            + "**TO DELETE AN EVENT USE THE /delete_alert command.**\n"
            + f"Updated at {datetime.datetime.now()}"
        )
        view = PromptInitial()

        await self.prompt_creator_schedule_lock.acquire()
        channel = self.get_channel(1150695270267486359)

        # check if there are any prompts in the channel already
        async for message in channel.history(limit=10):
            if message.author == self.user:
                # edit the message
                await message.edit(
                    content=content,
                    view=view,
                )
                self.prompt_creator_schedule_lock.release()
                return

        await channel.send(
            content=content,
            view=view,
        )
        self.prompt_creator_schedule_lock.release()

    @discord.ext.tasks.loop(seconds=15)
    async def send_alerts(self):
        for notification in database_controller.get_pending_notifications():
            message_text = notification.text
            message_embed = discord.Embed(
                title=notification.text,
                description="",
                color=discord.Color.red(),
            )

            if (
                database_controller.get_user_preference(
                    notification["user_id"], "delivery_method"
                )
                == "discord_DM"
            ):
                user = await self.fetch_user(notification["user_id"])
                try:
                    await user.send(message_text, embed=message_embed)
                    notification.mark_sent()
                except discord.errors.Forbidden as e:
                    print(
                        f"Could not send DM to {user.name}#{user.discriminator} ({user.id}) {e}, {type(e)}"
                    )
                    database_controller.set_user_preference(
                        notification["user_id"], "delivery_method", "discord_channel"
                    )
                    database_controller.send_notification(
                        repr((time.time(), os.urandom(128))),
                        "Your preferred delivery method has been set to Discord channel because you could not receive DMs from mutual server members.",
                    )
            else:
                # get channel that has name "notification_delivery_{user_id}"
                channel_name = f"notification_delivery_{notification['user_id']}"
                channel = discord.utils.get(self.get_all_channels(), name=channel_name)
                if channel is None:
                    # create channel
                    channel = await self.get_guild(
                        1150694755618009168
                    ).create_text_channel(name=channel_name)
                    # set channel to private so only the user can see it
                    await channel.set_permissions(
                        self.get_guild(1150694755618009168).default_role,
                        read_messages=False,
                    )
                    # get user object
                    user = await self.fetch_user(int(notification["user_id"]))
                    await channel.set_permissions(
                        user,
                        read_messages=True,
                    )
                await channel.send(message_text, embed=message_embed)
                notification.mark_sent()


def get_alerts_embed(user_id: int) -> discord.Embed:
    response_embed = discord.Embed(
        title="Your Alerts",
        description="Here are all of your alerts.",
        color=discord.Color.yellow(),
    )
    for alert in database_controller.get_alerts(user_id):
        response_embed.add_field(
            name=f"ID: {alert['id']}",
            value=f"{alert['route_number']} at {alert['departure_time']} in the {alert['direction']} direction",
            inline=False,
        )
    return response_embed


class NewAlert(discord.ui.Modal, title="New Alert"):
    route_number = discord.ui.TextInput(
        label="Route Number (required)", placeholder='E.G. "X50", "502"'
    )

    originate_time = discord.ui.TextInput(
        label="Origin Departure Time (24-hour time)",
        placeholder='E.G. "13:12", "21:27"',
    )

    direction = discord.ui.TextInput(
        label="Direction",
        placeholder='Write "IN" or "OUT"',
    )

    async def on_submit(self, interaction: discord.Interaction):
        if (
            self.route_number.value == ""
            or self.originate_time.value == ""
            or self.direction.value == ""
        ):
            await interaction.response.send_message(
                "Please fill out all fields.", ephemeral=True
            )
            return
        if self.direction.value.lower() not in ["in", "out"]:
            await interaction.response.send_message(
                'Please write "IN" or "OUT" for the direction.', ephemeral=True
            )
            return
        if self.originate_time.value.count(":") != 1:
            await interaction.response.send_message(
                "Please write the origination time in the format HH:MM.", ephemeral=True
            )
            return
        if self.route_number.value.startswith("2"):
            await interaction.response.send_message(
                "School routes are extremly unlikely to be listed in the cancellations list on Metro's site, expect this to be inaccurate.",
                ephemeral=True,
            )
        database_controller.add_alert(
            interaction.user.id,
            self.route_number.value,
            self.originate_time.value,
            self.direction.value,
        )
        await interaction.response.send_message(
            f"Your alert for the {self.route_number.value} bus at {self.originate_time.value} in the {self.direction.value} direction has been created.",
            embed=get_alerts_embed(interaction.user.id),
            view=Prompt(),
            ephemeral=True,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            "Oops! Something went wrong.", ephemeral=True
        )

        # Make sure we know what the error actually is
        traceback.print_exception(type(error), error, error.__traceback__)


class DeliveryMethodMenu(discord.ui.View):
    @discord.ui.button(label="Discord DM", style=discord.ButtonStyle.secondary)
    async def discord_DM(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        database_controller.set_user_preference(
            interaction.user.id, "delivery_method", "discord_DM"
        )
        database_controller.send_mail(
            interaction.user.id,
            None,
            None,
            None,
            "Your preferred delivery method has been set to Discord DM.",
        )
        await interaction.response.send_message(
            "Your preferred delivery method has been set to Discord DM.",
            ephemeral=True,
        )

    @discord.ui.button(label="Discord Channel", style=discord.ButtonStyle.secondary)
    async def discord_channel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        database_controller.set_user_preference(
            interaction.user.id, "delivery_method", "discord_channel"
        )
        database_controller.send_mail(
            interaction.user.id,
            None,
            None,
            None,
            "Your preferred delivery method has been set to Discord channel.",
        )
        await interaction.response.send_message(
            "Your preferred delivery method has been set to Discord channel.",
            ephemeral=True,
        )


class Prompt(discord.ui.View):
    @discord.ui.button(label="Create Alert", style=discord.ButtonStyle.green)
    async def create_alert(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(NewAlert())

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def view_alerts(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            embed=get_alerts_embed(interaction.user.id), view=Prompt(), ephemeral=True
        )

    @discord.ui.button(label="Send test alert", style=discord.ButtonStyle.secondary)
    async def test_alert(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        database_controller.test_mail(interaction.user.id)
        await interaction.response.send_message(
            "Test alert sent. If you do not receive it, check that you can receive DMs from mutual server members.",
            embed=get_alerts_embed(interaction.user.id),
            view=Prompt(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Change delivery method", style=discord.ButtonStyle.secondary
    )
    async def change_delivery_method(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "Please select your preferred delivery method.",
            view=DeliveryMethodMenu(),
            ephemeral=True,
        )


class PromptInitial(Prompt):
    @discord.ui.button(label="View Alerts", style=discord.ButtonStyle.primary)
    async def view_alerts(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            embed=get_alerts_embed(interaction.user.id), view=Prompt(), ephemeral=True
        )


client = SubscribeClient()


@client.tree.command()
@discord.app_commands.describe(
    alert_id="The ID of the alert you want to delete.",
)
async def delete_alert(
    interaction: discord.Interaction,
    alert_id: int,
):
    if database_controller.delete_alert(interaction.user.id, alert_id):
        await interaction.response.send_message(
            f"Alert with ID {alert_id} has been deleted.",
            embed=get_alerts_embed(interaction.user.id),
            view=Prompt(),
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"Alert with ID {alert_id} does not exist.",
            embed=get_alerts_embed(interaction.user.id),
            view=Prompt(),
            ephemeral=True,
        )


client.run(sys.argv[1])
