import logging
from datetime import datetime, timezone

import discord

from .availability import (
    DAYS, DAY_KEYS, current_status, format_interval, parse_schedule_fields,
    validate_intervals, weekly_hours,
)
from .time_utils import format_hour, get_timezone


log = logging.getLogger("tzone.commands")
DAY_GROUPS = (("wed", "thu"), ("fri", "sat"), ("sun",))


def _member_name(guild: discord.Guild, user_id: str) -> str:
    member = guild.get_member(int(user_id))
    return member.display_name if member else f"Member {user_id[-4:]}"


class ContinueWizardView(discord.ui.View):
    def __init__(self, store, drafts, key, group_index):
        super().__init__(timeout=300)
        self.store = store
        self.drafts = drafts
        self.key = key
        self.group_index = group_index
        days = DAY_GROUPS[group_index]
        label = "Continue: " + " & ".join(DAYS[DAY_KEYS.index(day)] for day in days)
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
        button.callback = self.continue_setup
        self.add_item(button)

    async def continue_setup(self, interaction: discord.Interaction):
        if (str(interaction.guild_id), str(interaction.user.id)) != self.key:
            await interaction.response.send_message(
                "This setup belongs to another member. Run /set_zone to start your own.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            DaysModal(self.store, self.drafts, self.key, self.group_index)
        )


class TimezoneModal(discord.ui.Modal, title="Timezone and Monday/Tuesday"):
    def __init__(self, store, drafts, key):
        super().__init__(timeout=300)
        self.store = store
        self.drafts = drafts
        self.key = key
        self.timezone_field = discord.ui.TextInput(
            label="IANA timezone", placeholder="Africa/Algiers", max_length=80
        )
        self.add_item(self.timezone_field)
        self.fields = {}
        for day in ("mon", "tue"):
            for status in ("free", "chat"):
                field = discord.ui.TextInput(
                    label=f"{DAYS[DAY_KEYS.index(day)]} {status.title()} hours",
                    placeholder="09-14, 18-21 (blank = unavailable)",
                    required=False, max_length=100,
                )
                self.fields[f"{day}_{status}"] = field
                self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            timezone_name = self.timezone_field.value.strip()
            get_timezone(timezone_name)
            intervals = parse_schedule_fields({
                key: field.value for key, field in self.fields.items()
            })
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        self.drafts[self.key] = {
            "timezone": timezone_name,
            "intervals": intervals,
        }
        await interaction.response.send_message(
            "First step saved. Continue to Wednesday and Thursday.",
            view=ContinueWizardView(self.store, self.drafts, self.key, 0),
            ephemeral=True,
        )


class DaysModal(discord.ui.Modal):
    def __init__(self, store, drafts, key, group_index):
        days = DAY_GROUPS[group_index]
        title = "Availability: " + " & ".join(DAYS[DAY_KEYS.index(day)] for day in days)
        super().__init__(title=title, timeout=300)
        self.store = store
        self.drafts = drafts
        self.key = key
        self.group_index = group_index
        self.fields = {}
        for day in days:
            for status in ("free", "chat"):
                field = discord.ui.TextInput(
                    label=f"{DAYS[DAY_KEYS.index(day)]} {status.title()} hours",
                    placeholder="09-14, 18-21 (blank = unavailable)",
                    required=False, max_length=100,
                )
                self.fields[f"{day}_{status}"] = field
                self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        draft = self.drafts.get(self.key)
        if draft is None:
            await interaction.response.send_message(
                "This setup expired. Run /set_zone again.", ephemeral=True
            )
            return
        try:
            added = parse_schedule_fields({
                key: field.value for key, field in self.fields.items()
            })
            combined = draft["intervals"] + added
            validate_intervals(combined)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        draft["intervals"] = combined
        if self.group_index + 1 < len(DAY_GROUPS):
            next_days = DAY_GROUPS[self.group_index + 1]
            label = "Continue to " + " & ".join(
                DAYS[DAY_KEYS.index(day)] for day in next_days
            )
            await interaction.response.send_message(
                f"Saved. {label}.",
                view=ContinueWizardView(
                    self.store, self.drafts, self.key, self.group_index + 1
                ),
                ephemeral=True,
            )
            return

        try:
            await self.store.save_user_schedule(
                self.key[0], self.key[1], draft["timezone"], draft["intervals"]
            )
        except Exception:
            log.exception("Could not save schedule for user %s", self.key[1])
            await interaction.response.send_message(
                "I couldn't save your schedule. Please try again.", ephemeral=True
            )
            return

        self.drafts.pop(self.key, None)
        await interaction.response.send_message(
            f"Saved timezone **{draft['timezone']}** and all seven days. "
            "Your nickname refreshes each local hour.",
            ephemeral=True,
        )


class ListPager(discord.ui.View):
    def __init__(self, title: str, pages: list[str], timezone_name: str):
        super().__init__(timeout=180)
        self.title = title
        self.pages = pages or ["No matching members right now."]
        self.timezone_name = timezone_name
        self.index = 0
        self.previous_button = discord.ui.Button(
            label="Previous", style=discord.ButtonStyle.secondary
        )
        self.next_button = discord.ui.Button(
            label="Next", style=discord.ButtonStyle.secondary
        )
        self.previous_button.callback = self.previous
        self.next_button.callback = self.next
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self._sync()

    def _sync(self):
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index >= len(self.pages) - 1

    def embed(self):
        embed = discord.Embed(
            title=self.title, description=self.pages[self.index],
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"Page {self.index + 1}/{len(self.pages)} · {self.timezone_name}"
        )
        return embed

    async def previous(self, interaction):
        self.index = max(0, self.index - 1)
        self._sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def next(self, interaction):
        self.index = min(len(self.pages) - 1, self.index + 1)
        self._sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class WeeklyPager(discord.ui.View):
    def __init__(self, title: str, pages: list[tuple[str, str]], timezone_name: str):
        super().__init__(timeout=300)
        self.title = title
        self.pages = pages
        self.timezone_name = timezone_name
        self.index = 0
        self.previous_button = discord.ui.Button(
            label="Previous day", style=discord.ButtonStyle.secondary
        )
        self.next_button = discord.ui.Button(
            label="Next day", style=discord.ButtonStyle.secondary
        )
        self.previous_button.callback = self.previous
        self.next_button.callback = self.next
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self._sync()

    def _sync(self):
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index == len(self.pages) - 1

    def embed(self):
        description, footer = self.pages[self.index]
        embed = discord.Embed(
            title=f"{self.title} · {DAYS[self.index]}",
            description=description, color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{footer} · {self.timezone_name}")
        return embed

    async def previous(self, interaction):
        self.index = max(0, self.index - 1)
        self._sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def next(self, interaction):
        self.index = min(len(self.pages) - 1, self.index + 1)
        self._sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)


def register_commands(bot, store, drafts):
    @bot.tree.command(name="set_zone", description="Set your timezone and weekly Free/Chat hours")
    async def set_zone(interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use this command inside a server.", ephemeral=True
            )
            return
        key = (str(interaction.guild_id), str(interaction.user.id))
        await interaction.response.send_modal(TimezoneModal(store, drafts, key))

    @bot.tree.command(name="delete_zone", description="Delete your saved timezone and schedule")
    async def delete_zone(interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use this command inside a server.", ephemeral=True
            )
            return
        await store.delete_user(str(interaction.guild_id), str(interaction.user.id))
        await interaction.response.send_message(
            "Your timezone and schedule were deleted. Nickname updates are disabled.",
            ephemeral=True,
        )

    @bot.tree.command(name="whos_free", description="See who is Free right now")
    async def whos_free(interaction: discord.Interaction):
        await show_current(interaction, store, "free")

    @bot.tree.command(name="whos_chat", description="See who is available to chat right now")
    async def whos_chat(interaction: discord.Interaction):
        await show_current(interaction, store, "chat")

    @bot.tree.command(name="weekly_free", description="See the weekly Free availability heatmap")
    async def weekly_free(interaction: discord.Interaction):
        await show_weekly(interaction, store, "free")

    @bot.tree.command(name="weekly_chat", description="See the weekly Chat availability heatmap")
    async def weekly_chat(interaction: discord.Interaction):
        await show_weekly(interaction, store, "chat")


async def show_current(interaction: discord.Interaction, store, mode: str):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Use this command inside a server.", ephemeral=True
        )
        return
    requester_timezone = await store.get_user_timezone(
        str(interaction.guild.id), str(interaction.user.id)
    )
    if not requester_timezone:
        await interaction.response.send_message(
            "Set your timezone first with /set_zone.", ephemeral=True
        )
        return

    profiles = await store.get_guild_schedules(str(interaction.guild.id))
    now = datetime.now(timezone.utc)
    entries = []
    for profile in profiles:
        local_now = now.astimezone(get_timezone(profile["timezone"]))
        status, interval = current_status(profile["intervals"], local_now)
        if status == "free" or (mode == "chat" and status == "chat"):
            label = "Free" if status == "free" else "Chat-only"
            entries.append(
                f"**{_member_name(interaction.guild, profile['user_id'])}** — "
                f"{label} ({format_interval(interval)})"
            )

    entries.sort(key=str.casefold)
    pages = [
        "\n".join(entries[index:index + 10])
        for index in range(0, len(entries), 10)
    ] or ["No members match this status right now."]
    requester_now = now.astimezone(get_timezone(requester_timezone))
    pages[0] = f"Current time: **{format_hour(requester_now)}**\n\n" + pages[0]
    title = "Who's Free right now" if mode == "free" else "Who's available to Chat"
    view = ListPager(title, pages, requester_timezone)
    await interaction.response.send_message(
        embed=view.embed(), view=view, ephemeral=True
    )


async def show_weekly(interaction: discord.Interaction, store, mode: str):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Use this command inside a server.", ephemeral=True
        )
        return
    requester_timezone = await store.get_user_timezone(
        str(interaction.guild.id), str(interaction.user.id)
    )
    if not requester_timezone:
        await interaction.response.send_message(
            "Set your timezone first with /set_zone.", ephemeral=True
        )
        return

    profiles = await store.get_guild_schedules(str(interaction.guild.id))
    pages = []
    for weekday in range(7):
        target_date, rows = weekly_hours(profiles, requester_timezone, weekday)
        lines = [
            f"{item['color']} **{format_hour(item['hour'])}** — "
            f"{item['free']} Free · {item['chat']} Chat-only"
            for item in rows
        ]
        best = max((item["free"] for item in rows), default=0)
        best_slots = [
            format_hour(item["hour"])
            for item in rows if item["free"] == best and best > 0
        ]
        best_text = ", ".join(best_slots) if best_slots else "No Free slot found"
        description = "\n".join(lines)
        description += f"\n\n**Best Time (Free):** {best_text} · {best} people"
        if mode == "chat":
            description += "\n*Chat-only members are included in the hourly counts.*"
        pages.append((
            description,
            f"{target_date.isoformat()} · Best Free overlap: {best}",
        ))

    title = "Weekly Free heatmap" if mode == "free" else "Weekly Chat heatmap"
    view = WeeklyPager(title, pages, requester_timezone)
    await interaction.response.send_message(
        embed=view.embed(), view=view, ephemeral=True
    )
