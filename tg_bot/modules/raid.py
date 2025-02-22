# Raid module by itsLuuke (t.me/itsLuuke)
import html
from typing import Optional
from datetime import timedelta
from pytimeparse.timeparse import timeparse

from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.ext import CallbackContext
from telegram.utils.helpers import mention_html

from .log_channel import loggable

from .helper_funcs.chat_status import connection_status
from .helper_funcs.decorators import kigcmd, kigcallback
from .cron_jobs import j
from ..import spamcheck, log
from .helper_funcs.admin_status import (
    user_admin_check,
    bot_admin_check,
    AdminPerms,
    get_bot_member,
    bot_is_admin,
    user_is_admin,
    user_not_admin_check,
)
import tg_bot.modules.sql.welcome_sql as sql

# store job id in a dict to be able to cancel them later
RUNNING_RAIDS = {} # {chat_id:job_id, ...}

def get_time(time: str) -> int:
    try:
        return timeparse(time)
    except:
        return 0

def get_readable_time(time: int) -> str:
    t = f"{timedelta(seconds=time)}".split(":")
    if time == 86400:
        return "1 day"
    return "{} hour(s)".format(t[0]) if time>=3600 else "{} minutes".format(t[1])

@kigcmd(command="raid", pass_args=True)
@spamcheck
@connection_status
@bot_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS)
@user_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS, allow_mods = True)
@loggable
def setRaid(update: Update, context: CallbackContext) -> Optional[str]:
    args = context.args
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user
    if chat.type == "private":
        context.bot.sendMessage(chat.id, "This command is not available in PMs.")
        return
    stat, time, acttime = sql.getRaidStatus(chat.id)
    readable_time = get_readable_time(time)
    if len(args) == 0:
        if stat:
            text = 'Raid mode is currently <code>Enabled</code>\nWould you like to <code>Disable</code> raid?'
            keyboard = [[
                InlineKeyboardButton("Disable Raid Mode",callback_data="disable_raid={}={}".format(chat.id, time)), 
                InlineKeyboardButton("Cancel Action",callback_data="cancel_raid=1"), 
                ]]
        else:
            text = f"Raid mode is currently <code>Disabled</code>\nWould you like to <code>Enable</code> raid for {readable_time}?"
            keyboard = [[
                InlineKeyboardButton("Enable Raid Mode",callback_data="enable_raid={}={}".format(chat.id, time)), 
                InlineKeyboardButton("Cancel Action",callback_data="cancel_raid=0"), 
                ]] 
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    elif args[0] == "off":
        if stat:
            sql.setRaidStatus(chat.id, False, time, acttime)
            j.scheduler.remove_job(RUNNING_RAIDS.pop(int(chat.id)))
            text = "Raid mode has been <code>Disabled</code>, members that join will no longer be kicked."
            msg.reply_text(text, parse_mode=ParseMode.HTML)
            return (
            f"<b>{html.escape(chat.title)}:</b>\n"
            f"#RAID\n"
            f"Disabled\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n")

    else:
        args_time = args[0].lower()
        if time := get_time(args_time):
            readable_time = get_readable_time(time)
            if time >= 300 and time < 86400:
                text = f"Raid mode is currently <code>Disabled</code>\nWould you like to <code>Enable</code> raid for {readable_time}?"
                keyboard = [[
                    InlineKeyboardButton("Enable Raid",callback_data="enable_raid={}={}".format(chat.id, time)), 
                    InlineKeyboardButton("Cancel Action",callback_data="cancel_raid=0"), 
                    ]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                msg.reply_text("You can only set time between 5 minutes and 1 day", parse_mode=ParseMode.HTML)

        else:
            msg.reply_text("Unknown time given, give me something like 5m or 1h", parse_mode=ParseMode.HTML)

@kigcallback(pattern="enable_raid=")
@connection_status
@user_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS, allow_mods = True, noreply=True)
@loggable
def enable_raid_cb(update: Update, ctx: CallbackContext) -> Optional[str]:
    args = update.callback_query.data.replace("enable_raid=","").split("=")
    chat = update.effective_chat
    user = update.effective_user
    chat_id = args[0]
    time = int(args[1])
    readable_time = get_readable_time(time)
    _, t, acttime = sql.getRaidStatus(chat_id)
    sql.setRaidStatus(chat_id, True, time, acttime)
    update.effective_message.edit_text(f"Raid mode has been <code>Enabled</code> for {readable_time}.", parse_mode=ParseMode.HTML)
    log.info("enabled raid mode in {} for {}".format(chat_id, readable_time))
    try:
        oldRaid = RUNNING_RAIDS.pop(int(chat_id))
        j.scheduler.remove_job(oldRaid) # check if there was an old job
    except KeyError:
        pass
    def disable_raid(_):
        sql.setRaidStatus(chat_id, False, t, acttime)
        log.info("disbled raid mode in {}".format(chat_id))
        ctx.bot.send_message(chat_id, "Raid mode has been automatically disabled!")
    raid = j.run_once(disable_raid, time)
    RUNNING_RAIDS[int(chat_id)] = raid.job.id
    return (
        f"<b>{html.escape(chat.title)}:</b>\n"
        f"#RAID\n"
        f"Enabled for {readable_time}\n"
        f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
    )

@kigcallback(pattern="disable_raid=")
@connection_status
@user_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS, allow_mods = True, noreply=True)
@loggable
def disable_raid_cb(update: Update, _: CallbackContext) -> Optional[str]:
    args = update.callback_query.data.replace("disable_raid=","").split("=")
    chat = update.effective_chat
    user = update.effective_user
    chat_id = args[0]
    time = args[1]
    _, _, acttime = sql.getRaidStatus(chat_id)
    sql.setRaidStatus(chat_id, False, time, acttime)
    j.scheduler.remove_job(RUNNING_RAIDS.pop(int(chat_id)))
    update.effective_message.edit_text(
        'Raid mode has been <code>Disabled</code>, joinig members will no longer be kicked.',
        parse_mode=ParseMode.HTML,
    )
    logmsg = (
        f"<b>{html.escape(chat.title)}:</b>\n"
        f"#RAID\n"
        f"Disabled\n"
        f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
    )
    return logmsg

@kigcallback(pattern="cancel_raid=")
@connection_status
@user_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS, allow_mods = True, noreply=True)
def disable_raid_cb(update: Update, _: CallbackContext):
    args = update.callback_query.data.split("=")
    what = args[0]
    update.effective_message.edit_text(f"Action cancelled, Raid mode will stay <code>{'Enabled' if what ==1 else 'Disabled'}</code>.", parse_mode=ParseMode.HTML)

@kigcmd(command="raidtime")
@spamcheck
@connection_status
@bot_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS)
@user_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS, allow_mods = True)
@loggable
def raidtime(update: Update, context: CallbackContext) -> Optional[str]:
    what, time, acttime = sql.getRaidStatus(update.effective_chat.id)
    args = context.args
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not args:
        msg.reply_text(f"Raid mode is currently set to {get_readable_time(time)}\nWhen toggled, the raid mode will last for {get_readable_time(time)} then turn off automatically", parse_mode=ParseMode.HTML)
        return
    args_time = args[0].lower()
    if time := get_time(args_time):
        readable_time = get_readable_time(time)
        if time >= 300 and time < 86400:
            text = f"Raid mode is currently set to {readable_time}\nWhen toggled, the raid mode will last for {readable_time} then turn off automatically"
            msg.reply_text(text, parse_mode=ParseMode.HTML)
            sql.setRaidStatus(chat.id, what, time, acttime)
            return (f"<b>{html.escape(chat.title)}:</b>\n"
            f"#RAID\n"
            f"Set Raid mode time to {readable_time}\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n")
        else:
            msg.reply_text("You can only set time between 5 minutes and 1 day", parse_mode=ParseMode.HTML)
    else:
        msg.reply_text("Unknown time given, give me something like 5m or 1h", parse_mode=ParseMode.HTML)

@kigcmd(command="raidactiontime", pass_args=True)
@spamcheck
@connection_status
@bot_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS)
@user_admin_check(AdminPerms.CAN_RESTRICT_MEMBERS, allow_mods = True)
@loggable
def raidtime(update: Update, context: CallbackContext) -> Optional[str]:
    what, t, time = sql.getRaidStatus(update.effective_chat.id)
    args = context.args
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not args:
        msg.reply_text(f"Raid action time is currently set to {get_readable_time(time)}\nWhen toggled, the members that join will be temp banned for {get_readable_time(time)}", parse_mode=ParseMode.HTML)
        return
    args_time = args[0].lower()
    if time := get_time(args_time):
        readable_time = get_readable_time(time)
        if time >= 300 and time < 86400:
            text = f"Raid action time is currently set to {get_readable_time(time)}\nWhen toggled, the members that join will be temp banned for {readable_time}"
            msg.reply_text(text, parse_mode=ParseMode.HTML)
            sql.setRaidStatus(chat.id, what, t, time)
            return (f"<b>{html.escape(chat.title)}:</b>\n"
            f"#RAID\n"
            f"Set Raid mode action time to {readable_time}\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n")
        else:
            msg.reply_text("You can only set time between 5 minutes and 1 day", parse_mode=ParseMode.HTML)
    else:
        msg.reply_text("Unknown time given, give me something like 5m or 1h", parse_mode=ParseMode.HTML)

from .language import gs

def get_help(chat):
    return gs(chat, "raid_help")

__mod_name__ = "AntiRaid"
