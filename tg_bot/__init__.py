import logging
import os
import sys
import time
from typing import List
import spamwatch
import telegram.ext as tg
from telegram.ext import Dispatcher
from telethon import TelegramClient
from telethon.sessions import MemorySession
from configparser import ConfigParser
from ptbcontrib.postgres_persistence import PostgresPersistence
from logging.config import fileConfig
from functools import wraps
from SibylSystem import PsychoPass
StartTime = time.time()

def get_user_list(key):
    # Import here to evade a circular import
    from tg_bot.modules.sql import nation_sql
    royals = nation_sql.get_royals(key)
    return [a.user_id for a in royals]

# enable logging

fileConfig('logging.ini')

log = logging.getLogger('[Enterprise]')
logging.getLogger('ptbcontrib.postgres_persistence.postgrespersistence').setLevel(logging.WARNING)
log.info("[LOGGER] LOGGER is starting. | Licensed under GPLv3.")
log.info("[LOGGER] Project maintained by: github.com/itsLuuke (t.me/itsLuuke)")

# if version < 3.6, stop bot.
if sys.version_info[0] < 3 or sys.version_info[1] < 7:
    log.error(
        "[LOGGER] You MUST have a python version of at least 3.7! Multiple features depend on this. Bot quitting."
    )
    quit(1)

parser = ConfigParser()
parser.read("config.ini")
kigconfig = parser["kigconfig"]

class KigyoINIT:
    def __init__(self, parser: ConfigParser):
        self.parser = parser
        self.SYS_ADMIN: int = self.parser.getint('SYS_ADMIN', 0)
        self.OWNER_ID: int = self.parser.getint('OWNER_ID')
        self.OWNER_USERNAME: str = self.parser.get('OWNER_USERNAME', None)
        self.APP_ID: str = self.parser.getint("APP_ID")
        self.API_HASH: str = self.parser.get("API_HASH")
        self.WEBHOOK: bool = self.parser.getboolean('WEBHOOK', False)
        self.URL: str = self.parser.get('URL', None)
        self.CERT_PATH: str = self.parser.get('CERT_PATH', None)
        self.PORT: int = self.parser.getint('PORT', None)
        self.INFOPIC: bool = self.parser.getboolean('INFOPIC', False)
        self.DEL_CMDS: bool = self.parser.getboolean("DEL_CMDS", False)
        self.STRICT_GBAN: bool = self.parser.getboolean("STRICT_GBAN", False)
        self.ALLOW_EXCL: bool = self.parser.getboolean("ALLOW_EXCL", False)
        self.CUSTOM_CMD: List[str] = ['/', '!', ">"]
        self.BAN_STICKER: str = self.parser.get("BAN_STICKER", None)
        self.TOKEN: str = self.parser.get("TOKEN")
        self.DB_URI: str = self.parser.get("SQLALCHEMY_DATABASE_URI")
        self.LOAD = self.parser.get("LOAD").split()
        self.LOAD: List[str] = list(map(str, self.LOAD))
        self.MESSAGE_DUMP: int = self.parser.getint('MESSAGE_DUMP', None)
        self.GBAN_LOGS: int = self.parser.getint('GBAN_LOGS', None)
        self.NO_LOAD = self.parser.get("NO_LOAD").split()
        self.NO_LOAD: List[str] = list(map(str, self.NO_LOAD))
        self.spamwatch_api: str = self.parser.get('spamwatch_api', None)
        self.CASH_API_KEY: str = self.parser.get('CASH_API_KEY', None)
        self.TIME_API_KEY: str = self.parser.get('TIME_API_KEY', None)
        self.WALL_API: str = self.parser.get('WALL_API', None)
        self.LASTFM_API_KEY: str = self.parser.get('LASTFM_API_KEY', None)
        self.WEATHER_API: str = self.parser.get('WEATHER_API', None)
        self.CF_API_KEY: str =  self.parser.get("CF_API_KEY", None)
        self.bot_id = 0 #placeholder
        self.bot_name = " Ōɖìղ" #placeholder
        self.bot_username = "OdinRobot" #placeholder
        self.DEBUG: bool = self.parser.getboolean("IS_DEBUG", False)
        self.DROP_UPDATES: bool = self.parser.getboolean("DROP_UPDATES", True)
        self.BOT_API_URL: str = self.parser.get('BOT_API_URL', "https://api.telegram.org/bot")
        self.BOT_API_FILE_URL: str = self.parser.get('BOT_API_FILE_URL', "https://api.telegram.org/file/bot")

        self.ALLOW_CHATS =  self.parser.getboolean("ALLOW_CHATS", True)
        self.SUPPORT_GROUP =  self.parser.get("SUPPORT_GROUP", 0)
        self.IS_DEBUG =  self.parser.getboolean("IS_DEBUG", False)
        self.ANTISPAM_TOGGLE =  self.parser.getboolean("ANTISPAM_TOGGLE", True)
        self.GROUP_BLACKLIST =  self.parser.get("GROUP_BLACKLIST", [])
        self.GLOBALANNOUNCE =  self.parser.getboolean("GLOBALANNOUNCE", False)
        self.BACKUP_PASS =  self.parser.get("BACKUP_PASS", None)
        self.SIBYL_KEY =  self.parser.get("SIBYL_KEY", None)





    def init_sw(self):
        if self.spamwatch_api is None:
            log.warning("SpamWatch API key is missing! Check your config.ini")
            return None
        else:
            try:
                sw = spamwatch.Client(spamwatch_api)
                return sw
            except:
                sw = None
                log.warning("Can't connect to SpamWatch!")
                return sw


KInit = KigyoINIT(parser=kigconfig)

OWNER_ID = KInit.OWNER_ID
OWNER_USERNAME = KInit.OWNER_USERNAME
APP_ID = KInit.APP_ID
API_HASH = KInit.API_HASH
WEBHOOK = KInit.WEBHOOK
URL = KInit.URL
CERT_PATH = KInit.CERT_PATH
PORT = KInit.PORT
INFOPIC = KInit.INFOPIC
DEL_CMDS = KInit.DEL_CMDS
ALLOW_EXCL = KInit.ALLOW_EXCL
CUSTOM_CMD = KInit.CUSTOM_CMD
BAN_STICKER = KInit.BAN_STICKER
TOKEN = KInit.TOKEN
DB_URI = KInit.DB_URI
LOAD = KInit.LOAD
MESSAGE_DUMP = KInit.MESSAGE_DUMP
GBAN_LOGS = KInit.GBAN_LOGS
NO_LOAD = KInit.NO_LOAD
OWNER_USER = [OWNER_ID]
SYS_ADMIN = KInit.SYS_ADMIN
MOD_USERS = [OWNER_ID] + [SYS_ADMIN] + get_user_list("mods")
SUDO_USERS = [OWNER_ID] + [SYS_ADMIN] + get_user_list("sudos")
DEV_USERS = [OWNER_ID] + [SYS_ADMIN] + get_user_list("devs")
SUPPORT_USERS = get_user_list("supports")
WHITELIST_USERS = get_user_list("whitelists")
SPAMMERS = get_user_list("spammers")
spamwatch_api = KInit.spamwatch_api
CASH_API_KEY = KInit.CASH_API_KEY
TIME_API_KEY = KInit.TIME_API_KEY
# WALL_API = KInit.WALL_API
LASTFM_API_KEY = KInit.LASTFM_API_KEY
WEATHER_API = KInit.WEATHER_API
CF_API_KEY = KInit.CF_API_KEY
ALLOW_CHATS = KInit.ALLOW_CHATS
# SPB_MODE = kigconfig.getboolean('SPB_MODE', False)
SUPPORT_GROUP = KInit.SUPPORT_GROUP
IS_DEBUG = KInit.IS_DEBUG
GROUP_BLACKLIST = KInit.GROUP_BLACKLIST
ANTISPAM_TOGGLE = KInit.ANTISPAM_TOGGLE
bot_username = KInit.bot_username
GLOBALANNOUNCE = KInit.GLOBALANNOUNCE
BACKUP_PASS = KInit.BACKUP_PASS
SIBYL_KEY = KInit.SIBYL_KEY

BOT_ID = TOKEN.split(":")[0]


sibylClient: PsychoPass = None

if SIBYL_KEY:
    try:
        sibylClient = PsychoPass(SIBYL_KEY)
        logging.info("Connected to Sibyl System, NONA Tower")
    except Exception as e:
        sibylClient = None
        logging.warning(
            f"Failed to load SibylSystem due to {e.with_traceback(e.__traceback__)}",
        )


try:
    IS_DEBUG = IS_DEBUG
except AttributeError:
    IS_DEBUG = False

try:
    ANTISPAM_TOGGLE = ANTISPAM_TOGGLE
except AttributeError:
    ANTISPAM_TOGGLE = True

# SpamWatch
sw = KInit.init_sw()

from tg_bot.modules.sql import SESSION

if not KInit.DROP_UPDATES:
    updater = tg.Updater(token=TOKEN, base_url=KInit.BOT_API_URL, base_file_url=KInit.BOT_API_FILE_URL, workers=min(32, os.cpu_count() + 4), request_kwargs={"read_timeout": 10, "connect_timeout": 10}, persistence=PostgresPersistence(session=SESSION))
    
else:
    updater = tg.Updater(token=TOKEN, base_url=KInit.BOT_API_URL, base_file_url=KInit.BOT_API_FILE_URL, workers=min(32, os.cpu_count() + 4), request_kwargs={"read_timeout": 10, "connect_timeout": 10})
    
telethn = TelegramClient(MemorySession(), APP_ID, API_HASH)
dispatcher: Dispatcher = updater.dispatcher



# Load at end to ensure all prev variables have been set
from tg_bot.modules.helper_funcs.handlers import CustomCommandHandler

if CUSTOM_CMD and len(CUSTOM_CMD) >= 1:
    tg.CommandHandler = CustomCommandHandler


'''def spamfilters(text, user_id, chat_id):
    # print("{} | {} | {}".format(text, user_id, chat_id))
    if int(user_id) not in SPAMMERS:
        return False

    print("This user is a spammer!")
    return True'''


try:
    from tg_bot.antispam import antispam_restrict_user, antispam_cek_user, detect_user
    log.info("AntiSpam loaded!")
    antispam_module = True
except ModuleNotFoundError:
    antispam_module = False


def spamcheck(func):
    @wraps(func)
    def check_user(update, context, *args, **kwargs):
        try:
            chat = update.effective_chat
            user = update.effective_user
            message = update.effective_message
        except AttributeError:
            return
        # If msg from self, return True
        if user.id == context.bot.id:
            return False
        if user.id == "777000":
            return False
        if IS_DEBUG:
            print("{} | {} | {} | {}".format(message.text or message.caption, user.id, message.chat.title, chat.id))
        if antispam_module and ANTISPAM_TOGGLE:
            parsing_date = time.mktime(message.date.timetuple())
            detecting = detect_user(user.id, chat.id, message, parsing_date)
            if detecting:
                return False
            antispam_restrict_user(user.id, parsing_date)
        if int(user.id) in SPAMMERS:
            if IS_DEBUG:
                print("^ This user is a spammer!")
            return False
        elif str(chat.id) in GROUP_BLACKLIST:
            dispatcher.bot.sendMessage(chat.id, "This group is blacklisted, i'm outa here...")
            dispatcher.bot.leaveChat(chat.id)
            return False
        return func(update, context, *args, **kwargs)
    return check_user
