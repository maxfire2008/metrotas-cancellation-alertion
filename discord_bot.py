import datetime
import traceback
import discord
import discord.ext.tasks
import discord.ext.commands
import sys
import asyncio
import re
import DatabaseController
import discord.app_commands
import scraper

database_controller = DatabaseController.DatabaseController("sqlite:///database.db")

TEST_GUILD = discord.Object(1150694755618009168)


class SubscribeClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)

        self.prompt_creator_schedule_lock = asyncio.Lock()
        self.send_alerts_lock = asyncio.Lock()
        self.scrape_lock = asyncio.Lock()

        self.tree = discord.app_commands.CommandTree(self)

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        self.prompt_creator_schedule.start()
        self.send_alerts.start()
        self.scrape.start()
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="for cancellations"
            )
        )

    async def setup_hook(self) -> None:
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)

    @discord.ext.tasks.loop(seconds=60)
    async def prompt_creator_schedule(self):
        if self.prompt_creator_schedule_lock.locked():
            return
        await self.prompt_creator_schedule_lock.acquire()

        content = (
            """# MetroTas Cancellation Alerts
:warning: THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR FAILURE OR OTHER DEALINGS IN THE SOFTWARE.

## Creating alerts
To create an alert, use the "Create Alert" button below. You can leave fields blank to not use it for matches. i.e. if you want to match *all* X42 buses, don't fill in the time or direction.

## Deleting alerts
Simply use the /delete_alert command with the alert ID. You can find the alert ID by listing your alerts with the button below.

## Delivery methods
Notifications can be delivered via a channel in the Discord server, or via DMs. If you want to use DMs make sure to enable DMs from server members in the server settings.

## About me
I created this bot to help me know when my bus is delayed.
I'm available for freelance work. [Check out my resume](<https://mburgess.au/resume>)!
You can also checkout my [personal website](<https://maxstuff.net>) or my [YouTube channel](<https://maxstuff.net/youtube>)

## Support
Please get in touch with me@maxstuff.net or <@375884848294002689> if you need any help.

:warning: Make sure to read this message in full before use.\n"""
            + f"*Updated at {datetime.datetime.now()}*"
        )
        view = PromptInitial()

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
        if self.send_alerts_lock.locked():
            return
        await self.send_alerts_lock.acquire()
        for notification in database_controller.get_pending_notifications():
            message_text = notification.text

            if (
                database_controller.get_user_preference(
                    notification.recipient, "delivery_method"
                )
                == "discord_channel"
            ):
                # get channel that has name "notification_delivery_{user_id}"
                channel_name = f"notification_delivery_{notification.recipient}"
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
                    user = await self.fetch_user(int(notification.recipient))
                    await channel.set_permissions(
                        user,
                        read_messages=True,
                    )

                heading_exists = False
                heading_age = 0
                heading = "***" + notification.heading + "***\n"
                # check the previous messages to see if they have the same heading
                async for message in channel.history(limit=100):
                    if message.author == self.user:
                        # if it starts with the same heading
                        if message.content.startswith(heading):
                            heading_exists = True
                            break
                        else:
                            # check if there is a heading in the message
                            if re.findall(r"\*{3}.+\*{3}", message.content):
                                break
                            else:
                                heading_age += 1

                if heading_exists:
                    await channel.send(message_text)
                else:
                    await channel.send(
                        heading + message_text,
                    )
                database_controller.mark_notification_sent(notification.id)
            else:
                user = await self.fetch_user(notification.recipient)
                try:
                    heading_exists = False
                    heading_age = 0
                    heading = "***" + notification.heading + "***\n"
                    # check the previous messages to see if they have the same heading
                    async for message in user.history(limit=100):
                        if message.author == self.user:
                            # if it starts with the same heading
                            if message.content.startswith(heading):
                                heading_exists = True
                                break
                            else:
                                # check if there is a heading in the message
                                if re.findall(r"\*{3}.+\*{3}", message.content):
                                    break
                                else:
                                    heading_age += 1

                    if heading_exists:
                        await user.send(message_text)
                    else:
                        await user.send(
                            heading + message_text,
                        )

                    database_controller.mark_notification_sent(notification.id)
                except discord.errors.Forbidden as e:
                    print(
                        f"Could not send DM to {user.name}#{user.discriminator} ({user.id}) {e}, {type(e)}"
                    )
                    database_controller.set_user_preference(
                        notification.recipient, "delivery_method", "discord_channel"
                    )
                    database_controller.send_notification(
                        notification.recipient,
                        "Your preferred delivery method has been set to Discord channel because you could not receive DMs from mutual server members. If you want to use DMs make sure to enable DMs from server members in the server settings, then change the setting in #signup",
                    )

        self.send_alerts_lock.release()

    @discord.ext.tasks.loop(seconds=300)
    async def scrape(self):
        if self.scrape_lock.locked():
            return
        await self.scrape_lock.acquire()
        print("Scraping Metro website")
        scraper.main()
        self.scrape_lock.release()


def get_alerts_embed(user_id: int) -> discord.Embed:
    response_embed = discord.Embed(
        title="Your Alerts",
        description="Here are all of your alerts.",
        color=discord.Color.yellow(),
    )
    for alert in database_controller.get_alerts(user_id):
        message = ""
        if alert.route:
            message += f"The"
            if alert.direction:
                message += f" {alert.direction}bound"
            message += f" {alert.route}"
        else:
            message += "Any"
            if alert.direction:
                message += f" {alert.direction}bound"
            message += " bus"

        if alert.time:
            message += f" at {alert.time}"
        else:
            message += " at any time"

        if not alert.direction:
            message += ", inbound or outbound"

        response_embed.add_field(
            name=f"ID: {alert.id}",
            value=message,
            inline=False,
        )
    return response_embed


class NewAlert(discord.ui.Modal, title="New Alert"):
    route_number = discord.ui.TextInput(
        label="Route Number",
        placeholder='E.G. "X50", "502"',
        required=False,
    )

    originate_time = discord.ui.TextInput(
        label="Origin Departure Time (24-hour time)",
        placeholder='E.G. "13:12", "21:27"',
        required=False,
    )

    direction = discord.ui.TextInput(
        label="Direction",
        placeholder='Write "IN" or "OUT"',
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.direction.value.lower() not in ["in", "out", ""]:
            await interaction.response.send_message(
                'Please write "IN" or "OUT" for the direction.', ephemeral=True
            )
            return
        if (
            self.originate_time.value != ""
            and self.originate_time.value.count(":") != 1
        ):
            await interaction.response.send_message(
                "Please write the origination time in the format HH:MM (24-hour).",
                ephemeral=True,
            )
            return
        if self.route_number.value.startswith("2"):
            await interaction.response.send_message(
                "School routes are extremly unlikely to be listed in the cancellations list on Metro's site, expect this to be inaccurate.",
                ephemeral=True,
            )
        database_controller.new_alert(
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
        database_controller.send_notification(
            interaction.user.id,
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
        database_controller.send_notification(
            interaction.user.id,
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
        database_controller.send_notification(
            interaction.user.id,
            "This is a test alert.",
        )
        await interaction.response.send_message(
            "Test alert sent. If you do not receive it, check that you can receive DMs from server members.",
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
