import re, random
from html import escape
import html
from typing import Optional

import telegram
from telegram import ParseMode, InlineKeyboardMarkup, Message, InlineKeyboardButton
from telegram.error import BadRequest
from telegram.ext import (
    DispatcherHandlerStop,
    Filters,
)
from telegram.utils.helpers import  escape_markdown, mention_html

from tg_bot import dispatcher, log, SUDO_USERS, spamcheck

from .helper_funcs.extraction import extract_text
from .helper_funcs.filters import CustomFilters
from .helper_funcs.misc import build_keyboard_parser, revert_buttons
from .helper_funcs.msg_types import get_filter_type
from .helper_funcs.string_handling import (
    split_quotes,
    button_markdown_parser,
    escape_invalid_curly_brackets,
    markdown_to_html,
)
from .log_channel import loggable
from .sql import cust_filters_sql as sql

from .connection import connected

from .helper_funcs.alternate import send_message, typing_action
from .helper_funcs.decorators import kigcmd, kigmsg, kigcallback

from .helper_funcs.admin_status import (
    user_admin_check,
    AdminPerms,
    user_is_admin,
)

HANDLER_GROUP = 10

ENUM_FUNC_MAP = {
    sql.Types.TEXT.value: dispatcher.bot.send_message,
    sql.Types.BUTTON_TEXT.value: dispatcher.bot.send_message,
    sql.Types.STICKER.value: dispatcher.bot.send_sticker,
    sql.Types.DOCUMENT.value: dispatcher.bot.send_document,
    sql.Types.PHOTO.value: dispatcher.bot.send_photo,
    sql.Types.AUDIO.value: dispatcher.bot.send_audio,
    sql.Types.VOICE.value: dispatcher.bot.send_voice,
    sql.Types.VIDEO.value: dispatcher.bot.send_video,
    # sql.Types.VIDEO_NOTE.value: dispatcher.bot.send_video_note
}
CUSTFILTERS_GROUP = -2

@kigcmd(command='filters', admin_ok=True)
@spamcheck
@typing_action
def list_handlers(update, context):
    chat = update.effective_chat
    user = update.effective_user

    conn = connected(context.bot, update, chat, user.id, need_admin=False)
    if conn is not False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
        filter_list = "*Filter in {}:*\n"
    else:
        chat_id = update.effective_chat.id
        if chat.type == "private":
            chat_name = "Local filters"
            filter_list = "*local filters:*\n"
        else:
            chat_name = chat.title
            filter_list = "*Filters in {}*:\n"

    all_handlers = sql.get_chat_triggers(chat_id)

    if not all_handlers:
        send_message(
            update.effective_message, "No filters saved in {}!".format(chat_name)
        )
        return

    for keyword in all_handlers:
        entry = " • `{}`\n".format(escape_markdown(keyword))
        if len(entry) + len(filter_list) > telegram.MAX_MESSAGE_LENGTH:
            send_message(
                update.effective_message,
                filter_list.format(chat_name),
                parse_mode=telegram.ParseMode.MARKDOWN,
            )
            filter_list = entry
        else:
            filter_list += entry

    send_message(
        update.effective_message,
        filter_list.format(chat_name),
        parse_mode=telegram.ParseMode.MARKDOWN,
    )


# NOT ASYNC BECAUSE DISPATCHER HANDLER RAISED
@kigcmd(command='filter', run_async=False)
@spamcheck
@typing_action
@user_admin_check(AdminPerms.CAN_CHANGE_INFO)
@loggable
def filters(update, context) -> None:  # sourcery no-metrics
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    args = msg.text.split(
        None, 1
    )  # use python's maxsplit to separate Cmd, keyword, and reply_text



    conn = connected(context.bot, update, chat, user.id)
    if conn is not False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
    else:
        chat_id = update.effective_chat.id
        chat_name = "local filters" if chat.type == "private" else chat.title
    if not msg.reply_to_message and len(args) < 2:
        send_message(
            update.effective_message,
            "Please provide keyboard keyword for this filter to reply with!",
        )
        return

    if msg.reply_to_message:
        if len(args) < 2:
            send_message(
                update.effective_message,
                "Please provide keyword for this filter to reply with!",
            )
            return
        else:
            keyword = args[1]
    else:
        extracted = split_quotes(args[1])
        if len(extracted) < 1:
            return
        # set trigger -> lower, so as to avoid adding duplicate filters with different cases
        keyword = extracted[0].lower()

    # Add the filter
    # Note: perhaps handlers can be removed somehow using sql.get_chat_filters
    for handler in dispatcher.handlers.get(HANDLER_GROUP, []):
        if handler.filters == (keyword, chat_id):
            dispatcher.remove_handler(handler, HANDLER_GROUP)

    text, file_type, file_id = get_filter_type(msg)
    if not msg.reply_to_message and len(extracted) >= 2:
        offset = len(extracted[1]) - len(
            msg.text
        )  # set correct offset relative to command + notename
        text, buttons = button_markdown_parser(
            extracted[1], entities=msg.parse_entities(), offset=offset
        )
        text = text.strip()
        if not text:
            send_message(
                update.effective_message,
                "There is no filter message - You can't JUST have buttons, you need a message to go with it!",
            )
            return

    elif msg.reply_to_message and len(args) >= 2:
        if msg.reply_to_message.text:
            text_to_parsing = msg.reply_to_message.text
        elif msg.reply_to_message.caption:
            text_to_parsing = msg.reply_to_message.caption
        else:
            text_to_parsing = ""
        offset = len(
            text_to_parsing
        )  # set correct offset relative to command + notename
        text, buttons = button_markdown_parser(
            text_to_parsing, entities=msg.parse_entities(), offset=offset
        )
        text = text.strip()

    elif not text and not file_type:
        send_message(
            update.effective_message,
            "Please provide keyword for this filter reply with!",
        )
        return

    elif msg.reply_to_message:
        if msg.reply_to_message.text:
            text_to_parsing = msg.reply_to_message.text
        elif msg.reply_to_message.caption:
            text_to_parsing = msg.reply_to_message.caption
        else:
            text_to_parsing = ""
        offset = len(
            text_to_parsing
        )  # set correct offset relative to command + notename
        text, buttons = button_markdown_parser(
            text_to_parsing, entities=msg.parse_entities(), offset=offset
        )
        text = text.strip()
        if (msg.reply_to_message.text or msg.reply_to_message.caption) and not text:
            send_message(
                update.effective_message,
                "There is no note message - You can't JUST have buttons, you need a message to go with it!",
            )
            return

    else:
        send_message(update.effective_message, "Invalid filter!")
        return

    add = addnew_filter(update, chat_id, keyword, text, file_type, file_id, buttons)
    # This is an old method
    # sql.add_filter(chat_id, keyword, content, is_sticker, is_document, is_image, is_audio, is_voice, is_video, buttons)

    if add is True:
        send_message(
            update.effective_message,
            "Saved filter '{}' in *{}*!".format(keyword, chat_name),
            parse_mode=telegram.ParseMode.MARKDOWN,
        )
        logmsg = (
        f"<b>{html.escape(chat.title)}:</b>\n"
        f"#ADDFILTER\n"
        f"<b>Admin:</b> {mention_html(user.id, html.escape(user.first_name))}\n"
        f"<b>Note:</b> {keyword}"
        )
        return logmsg
    raise DispatcherHandlerStop


# NOT ASYNC BECAUSE DISPATCHER HANDLER RAISED
@kigcmd(command='stop', run_async=False)
@spamcheck
@typing_action
@user_admin_check(AdminPerms.CAN_CHANGE_INFO)
@loggable
def stop_filter(update, context) -> str:
    chat = update.effective_chat
    user = update.effective_user
    args = update.effective_message.text.split(None, 1)
    message = update.effective_message

    conn = connected(context.bot, update, chat, user.id)
    if conn is not False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
    else:
        chat_id = update.effective_chat.id
        chat_name = "Local filters" if chat.type == "private" else chat.title
    if len(args) < 2:
        send_message(update.effective_message, "What should i stop?")
        return ''

    chat_filters = sql.get_chat_triggers(chat_id)

    if not chat_filters:
        send_message(update.effective_message, "No filters active here!")
        return ''

    for keyword in chat_filters:
        if keyword == args[1]:
            sql.remove_filter(chat_id, args[1])
            send_message(
                update.effective_message,
                "Okay, I'll stop replying to that filter in *{}*.".format(chat_name),
                parse_mode=telegram.ParseMode.MARKDOWN,
            )
            logmsg = (
                    f"<b>{html.escape(chat.title)}:</b>\n"
                    f"#STOPFILTER\n"
                    f"<b>Admin:</b> {mention_html(user.id, html.escape(user.first_name))}\n"
                    f"<b>Filter:</b> {keyword}"
                )
            try:
                raise DispatcherHandlerStop
            finally:
                return logmsg

    send_message(
        update.effective_message,
        "That's not a filter - Click: /filters to get currently active filters.",
    )

@kigmsg((CustomFilters.has_text & ~Filters.update.edited_message), group=CUSTFILTERS_GROUP)
@spamcheck
def reply_filter(update, context):  # sourcery no-metrics
    chat = update.effective_chat  # type: Optional[Chat]
    message = update.effective_message  # type: Optional[Message]
    user = update.effective_user

    if not update.effective_user or update.effective_user.id == 777000:
        return
    to_match = extract_text(message)
    if not to_match:
        return

    chat_filters = sql.get_chat_triggers(chat.id)
    for keyword in chat_filters:
        pattern = r"( |^|[^\w])" + re.escape(keyword) + r"( |$|[^\w])"
        if re.search(pattern, to_match, flags=re.IGNORECASE):
            filt = sql.get_filter(chat.id, keyword)

            # print(keyword)
            # print(pattern)
            # print(to_match)
            if to_match.endswith("raw") and to_match.lower() == (keyword + (" raw" or " noformat")):
                no_format = True
                # print(" aaaa raw")
            else:
                no_format = False

            if filt.reply == "there is should be a new reply":
                buttons = sql.get_buttons(chat.id, filt.keyword)

                VALID_WELCOME_FORMATTERS = [
                    "first",
                    "last",
                    "fullname",
                    "username",
                    "id",
                    "chatname",
                    "mention",
                    "user",
                    "admin",
                ]
                if filt.reply_text:

                    if not no_format and "%%%" in filt.reply_text:
                        split = filt.reply_text.split("%%%")
                        if all(split):
                            text = random.choice(split)
                        else:
                            text = filt.reply_text
                    else:
                        text = filt.reply_text
                    if (text.startswith("~!") or text.startswith(" ~!")) and (text.endswith("!~") or text.endswith("!~ ")):
                        sticker_id = text.replace("~!", "").replace("!~", "").replace(" ", "") # replace space (' ') bcz, got error: Wrong remote file....
                        try:
                            context.bot.send_sticker(
                                chat.id,
                                sticker_id,
                                reply_to_message_id=message.message_id,
                            )
                            return
                        except BadRequest as excp:
                            if (
                                excp.message
                                == "Wrong remote file identifier specified: wrong padding in the string"
                            ):
                                context.bot.send_message(
                                    chat.id,
                                    "Message couldn't be sent, Is the sticker id valid?",
                                )
                                return
                            else:
                                log.exception("Error in filters: " + excp.message)
                                return

                    valid_format = escape_invalid_curly_brackets(
                        text, VALID_WELCOME_FORMATTERS
                    )
                    if valid_format:
                        filtext = valid_format.format(
                            first=escape(message.from_user.first_name),
                            last=escape(
                                message.from_user.last_name
                                or message.from_user.first_name
                            ),
                            fullname=" ".join(
                                [
                                    escape(message.from_user.first_name),
                                    escape(message.from_user.last_name),
                                ]
                                if message.from_user.last_name
                                else [escape(message.from_user.first_name)]
                            ),
                            username="@" + escape(message.from_user.username)
                            if message.from_user.username
                            else mention_html(
                                message.from_user.id, message.from_user.first_name
                            ),
                            mention=mention_html(
                                message.from_user.id, message.from_user.first_name
                            ),
                            chatname=escape(message.chat.title)
                            if message.chat.type != "private"
                            else escape(message.from_user.first_name),
                            id=message.from_user.id,
                            user="",
                            admin="",
                        )
                    else:
                        filtext = ""
                else:
                    filtext = ""

                if "{admin}" in filt.reply_text:
                    if user_is_admin(update, user.id):
                        return

                if "{user}" in filt.reply_text:
                    if not user_is_admin(update, user.id):
                        return

                keyb = []
                if no_format:
                    parse_mode = None
                    filtext += revert_buttons(buttons)
                    keyboard = InlineKeyboardMarkup(keyb)
                else:
                    parse_mode = ParseMode.HTML
                    keyb = build_keyboard_parser(context.bot, chat.id, buttons)
                    keyboard = InlineKeyboardMarkup(keyb)

                if filt.file_type in (sql.Types.BUTTON_TEXT, sql.Types.TEXT):
                    try:
                        context.bot.send_message(
                            chat.id,
                            markdown_to_html(filtext),
                            reply_to_message_id=message.message_id,
                            parse_mode=parse_mode,
                            disable_web_page_preview=True,
                            reply_markup=keyboard,
                        )
                    except BadRequest as excp:
                        error_catch = get_exception(excp, filt, chat)
                        if error_catch == "noreply":
                            try:
                                context.bot.send_message(
                                    chat.id,
                                    markdown_to_html(filtext),
                                    parse_mode=parse_mode,
                                    disable_web_page_preview=True,
                                    reply_markup=keyboard,
                                )
                            except BadRequest as excp:
                                log.exception("Error in filters: " + excp.message)
                                send_message(
                                    update.effective_message,
                                    get_exception(excp, filt, chat),
                                )
                        else:
                            try:
                                send_message(
                                    update.effective_message,
                                    get_exception(excp, filt, chat),
                                )
                            except BadRequest as excp:
                                log.exception(
                                    "Failed to send message: " + excp.message
                                )
                elif ENUM_FUNC_MAP[filt.file_type] == dispatcher.bot.send_sticker:
                    ENUM_FUNC_MAP[filt.file_type](
                        chat.id,
                        filt.file_id,
                        reply_to_message_id=message.message_id,
                        reply_markup=keyboard,
                    )
                else:
                    ENUM_FUNC_MAP[filt.file_type](
                        chat.id,
                        filt.file_id,
                        caption=markdown_to_html(filtext),
                        reply_to_message_id=message.message_id,
                        parse_mode=parse_mode,
                        reply_markup=keyboard,
                    )
            elif filt.is_sticker:
                message.reply_sticker(filt.reply)
            elif filt.is_document:
                message.reply_document(filt.reply)
            elif filt.is_image:
                message.reply_photo(filt.reply)
            elif filt.is_audio:
                message.reply_audio(filt.reply)
            elif filt.is_voice:
                message.reply_voice(filt.reply)
            elif filt.is_video:
                message.reply_video(filt.reply)
            elif filt.has_markdown:

                keyb = []
                buttons = sql.get_buttons(chat.id, filt.keyword)
                if no_format:
                    parse_mode = None
                    filt.reply += revert_buttons(buttons)
                    keyboard = InlineKeyboardMarkup(keyb)
                else:
                    parse_mode = ParseMode.MARKDOWN
                    keyb = build_keyboard_parser(context.bot, chat.id, buttons)
                    keyboard = InlineKeyboardMarkup(keyb)


                try:
                    send_message(
                        update.effective_message,
                        filt.reply,
                        parse_mode=parse_mode,
                        disable_web_page_preview=True,
                        reply_markup=keyboard,
                    )
                except BadRequest as excp:
                    if excp.message == "Unsupported url protocol":
                        try:
                            send_message(
                                update.effective_message,
                                "You seem to be trying to use an unsupported url protocol. "
                                "Telegram doesn't support buttons for some protocols, such as tg://. Please try "
                                "again...",
                            )
                        except BadRequest as excp:
                            log.exception("Error in filters: " + excp.message)
                    elif excp.message == "Reply message not found":
                        try:
                            context.bot.send_message(
                                chat.id,
                                filt.reply,
                                parse_mode=parse_mode,
                                disable_web_page_preview=True,
                                reply_markup=keyboard,
                            )
                        except BadRequest as excp:
                            log.exception("Error in filters: " + excp.message)
                    else:
                        try:
                            send_message(
                                update.effective_message,
                                "This message couldn't be sent as it's incorrectly formatted.",
                            )
                        except BadRequest as excp:
                            log.exception("Error in filters: " + excp.message)
                        log.warning(
                            "Message %s could not be parsed", str(filt.reply)
                        )
                        log.exception(
                            "Could not parse filter %s in chat %s",
                            str(filt.keyword),
                            str(chat.id),
                        )

            else:
                    # LEGACY - all new filters will have has_markdown set to True.
                try:
                    send_message(update.effective_message, filt.reply)
                except BadRequest as excp:
                    log.exception("Error in filters: " + excp.message)
            break

@kigcmd(command="removeallfilters", filters=Filters.chat_type.groups)
@spamcheck
def rmall_filters(update, context):
    chat = update.effective_chat
    user = update.effective_user
    member = chat.get_member(user.id)
    if member.status != "creator" and user.id not in SUDO_USERS:
        update.effective_message.reply_text(
            "Only the chat owner can clear all filters at once."
        )
    else:
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="Stop all filters", callback_data="filters_rmall"
                    )
                ],
                [InlineKeyboardButton(text="Cancel", callback_data="filters_cancel")],
            ]
        )
        update.effective_message.reply_text(
            f"Are you sure you would like to stop ALL filters in {chat.title}? This action cannot be undone.",
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN,
        )

@kigcallback(pattern=r"filters_.*")
@loggable
def rmall_callback(update, context) -> str:
    query = update.callback_query
    chat = update.effective_chat
    msg = update.effective_message
    member = chat.get_member(query.from_user.id)
    user = query.from_user
    if query.data == "filters_rmall":
        if member.status == "creator" or query.from_user.id in SUDO_USERS:
            allfilters = sql.get_chat_triggers(chat.id)
            if not allfilters:
                msg.edit_text("No filters in this chat, nothing to stop!")
                return ""

            count = 0
            filterlist = []
            for x in allfilters:
                count += 1
                filterlist.append(x)

            for i in filterlist:
                sql.remove_filter(chat.id, i)

            msg.edit_text(f"Cleaned {count} filters in {chat.title}")

            log_message = (
                f"<b>{html.escape(chat.title)}:</b>\n"
                f"#CLEAREDALLFILTERS\n"
                f"<b>Admin:</b> {mention_html(user.id, html.escape(user.first_name))}"
            )
            return log_message

        else:
            query.answer("Only owner of the chat can do this.")
            return ""

    elif query.data == "filters_cancel":
        if member.status == "creator" or query.from_user.id in SUDO_USERS:
            msg.edit_text("Clearing of all filters has been cancelled.")
            return ""
        else:
            query.answer("Only owner of the chat can do this.")
            return ""


# NOT ASYNC NOT A HANDLER
def get_exception(excp, filt, chat):
    if excp.message == "Unsupported url protocol":
        return "You seem to be trying to use the URL protocol which is not supported. Telegram does not support key for multiple protocols, such as tg: //. Please try again!"
    elif excp.message == "Reply message not found":
        return "noreply"
    else:
        log.warning("Message %s could not be parsed", str(filt.reply))
        log.exception(
            "Could not parse filter %s in chat %s", str(filt.keyword), str(chat.id)
        )
        return "This data could not be sent because it is incorrectly formatted."


# NOT ASYNC NOT A HANDLER
def addnew_filter(update, chat_id, keyword, text, file_type, file_id, buttons):
    msg = update.effective_message
    totalfilt = sql.get_chat_triggers(chat_id)
    if len(totalfilt) >= 150:  # Idk why i made this like function....
        msg.reply_text("This group has reached its max filters limit of 150.")
        return False
    else:
        sql.new_add_filter(chat_id, keyword, text, file_type, file_id, buttons)
        return True


def __stats__():
    return "• {} filters, across {} chats.".format(sql.num_filters(), sql.num_chats())


def __import_data__(chat_id, data):
    # set chat filters
    filters = data.get("filters", {})
    for trigger in filters:
        sql.add_to_blacklist(chat_id, trigger)


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    cust_filters = sql.get_chat_triggers(chat_id)
    return "There are `{}` custom filters here.".format(len(cust_filters))

from .language import gs

def get_help(chat):
    return gs(chat, "cust_filters_help")

__mod_name__ = "Filters"


# __handlers__ = [
#     HANDLER_GROUP,
# ]
