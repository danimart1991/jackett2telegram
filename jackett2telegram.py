import inspect
import argparse
import logging
import requests
import os
import sqlite3
import string
import unicodedata
import xml.etree.ElementTree as ElementTree
from datetime import datetime
from telegram import (
    Message,
    helpers,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
)
from telegram.ext.filters import MessageFilter
from typing import Any
from urllib import parse

blackhole_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "blackhole")
config_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "config")
db_path = os.path.join(config_path, "rss.db")
os.makedirs(blackhole_path, exist_ok=True)
os.makedirs(config_path, exist_ok=True)

rss_dict = {}

escaped_backslash = helpers.escape_markdown("-", 2)
char_limit = 255


class TopicFilter(MessageFilter):
    def filter(self, message: Message) -> bool | None:
        if message_thread_id is None:
            return True
        return (
            message.is_topic_message and message.message_thread_id == message_thread_id
        )


topic_filter = TopicFilter()


# SQLITE


def init_sqlite() -> None:
    logging.debug("Trying to create the Database")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS rss (name text PRIMARY KEY, link text, last_pubdate text, last_items text, is_down integer)"""
    )


def sqlite_connect() -> None:
    global conn
    conn = sqlite3.connect(db_path, check_same_thread=False)


def sqlite_load_all() -> list[Any]:
    sqlite_connect()
    c = conn.cursor()
    c.execute("SELECT * FROM rss")
    rows = c.fetchall()
    conn.close()
    return rows


def sqlite_write(
    name: str, link: str, last_pubdate: str, last_items: str, is_down: int
) -> None:
    sqlite_connect()
    c = conn.cursor()
    values = [(name), (link), (last_pubdate), (last_items), (is_down)]
    c.execute(
        """REPLACE INTO rss (name,link,last_pubdate,last_items,is_down) VALUES(?,?,?,?,?)""",
        values,
    )
    conn.commit()
    conn.close()


# RSS


def rss_load() -> None:
    # if the dict is not empty, empty it.
    if bool(rss_dict):
        rss_dict.clear()
    for row in sqlite_load_all():
        rss_dict[row[0]] = (row[1], row[2], row[3], row[4])


async def cmd_rss_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not its_me(update):
        return

    indexers = ["*List of Registered Indexers\.*"]
    if bool(rss_dict) is False:
        indexers.append("The database is empty\.")
    else:
        for rss_name, rss_props in sorted(rss_dict.items(), key=lambda item: item[0]):
            indexers.append(
                f"Title: {helpers.escape_markdown(rss_name, 2)}"
                + f"\nJacket RSS: `{helpers.escape_markdown(rss_props[0], 2)}`"
                + f"\nLast article from: {helpers.escape_markdown(rss_props[1], 2)}"
                + f"\nStatus: {('✔️' if rss_props[3] == 0 else '🚫' if rss_props[3] == 2 else '⚠️')}"
            )

    await telegram_send_reply_text(update, "\n\n".join(indexers))


async def cmd_rss_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not its_me(update):
        return

    if not context.args or not len(context.args) == 2:
        await telegram_send_reply_error(
            update,
            "To add a new _Jackett or Prowlarr RSS_ the command needs to be:\n`/add TITLE JACKETT_OR_PROWLARR_RSS_FEED_URL`",
        )
        return

    try:
        response = requests.get(context.args[1])
        root = ElementTree.fromstring(response.content)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []
    except ElementTree.ParseError:
        await telegram_send_reply_error(
            update,
            "The link does not seem to be a _Jackett or Prowlarr RSS Feed_ or is not supported\.",
        )
        return
    except requests.exceptions.MissingSchema:
        await telegram_send_reply_error(
            update, "The _Jackett or Prowlarr RSS Feed Url_ is malformed\."
        )
        return

    items.sort(
        reverse=True, key=lambda item: pubDate_to_datetime(item.findtext("pubDate", ""))
    )
    sqlite_write(
        context.args[0], context.args[1], items[0].findtext("pubDate", ""), str([]), 0
    )
    rss_load()
    logging.info(f"List: Indexer {context.args[0]} | {context.args[1]} added.")
    message = (
        f"*Indexer added to list:* {helpers.escape_markdown(context.args[0], 2)}"
        + f"\n`{helpers.escape_markdown(context.args[1], 2)}`"
    )
    await telegram_send_reply_text(update, message)


async def cmd_rss_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not its_me(update):
        return

    if not context.args or not len(context.args) == 1:
        await telegram_send_reply_error(
            update,
            "To remove a _Jackett or Prowlarr RSS_ the command needs to be:\n`/remove TITLE`",
        )
        return

    sqlite_connect()
    c = conn.cursor()
    q = (context.args[0],)
    escaped_indexer = helpers.escape_markdown(context.args[0], 2)
    try:
        c.execute("SELECT count(*) FROM rss WHERE name = ?", q)
        res = c.fetchall()[0][0]
        if not (int(res) == 1):
            await telegram_send_reply_error(
                update,
                f"Can't remove _Jackett or Prowlarr RSS_ with title _{escaped_indexer}_\. Not found\.",
            )
            return
        c.execute("DELETE FROM rss WHERE name = ?", q)
        conn.commit()
        conn.close()
    except sqlite3.Error:
        await telegram_send_reply_error(
            update,
            "Can't remove the _Jackett or Prowlarr RSS_ because of an unknown issue\.",
        )
        return
    rss_load()

    await telegram_send_reply_text(
        update, f"*Indexer removed from list:* {escaped_indexer}"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not its_me(update):
        return

    msg = (
        "*Jackett2Telegram \(Jackett and Prowlarr RSS to Telegram Bot\)*"
        + "\n\nAfter successfully adding a Jackett or Prowlarr RSS link, the bot starts fetching the feed every "
        f"{str(delay)} seconds\. \(This can be set\)"
        + "\n\nTitles are used to easily manage RSS feeds and should contain only one word and are case sensitive\."
        + "\n\nCommands:"
        + "\n\- /help \- Posts this help message\. 😑"
        + "\n\- /add TITLE JACKETT\_OR\_PROWLARR\_RSS\_FEED\_URL \- Adds new Jackett or Prowlarr RSS Feed \(overwrited if title previously exist\)\."
        + "\n\- /remove TITLE \- Removes the RSS link\."
        + "\n\- /list \- Lists all the titles and the asociated Jackett or Prowlarr RSS links from the DB\."
        + "\n\- /test JACKETT\_OR\_PROWLARR\_RSS\_FEED\_URL \- Inbuilt command that fetches a post \(usually latest\) from a Jackett or Prowlarr RSS\."
        + "\n\nIn order to use *Blackhole*, your _Torrent_ client must support it and be configured to point to *Jackett2Telegram* _Blackhole_ folder\."
        "\n\nIf you like the project, consider [BECOME A SPONSOR](https://github.com/sponsors/danimart1991)\."
    )

    if update.effective_message:
        await update.effective_message.reply_text(msg)
    elif context.bot:
        await context.bot.send_message(
            chat_id, msg, message_thread_id=message_thread_id
        )


async def rss_monitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    for rss_name, rss_props in rss_dict.items():
        try:
            response = requests.get(rss_props[0])
            root = ElementTree.fromstring(response.content)
            if root.tag == "error":
                code = root.attrib["code"]
                description = root.attrib["description"]
                if code == "410":
                    logging.info(f"Indexer {rss_name} is disabled.")
                    sqlite_write(rss_name, rss_props[0], rss_props[1], rss_props[2], 2)
                else:
                    raise Exception(f"{code}: {description}")
            else:
                channel = root.find("channel")
                items = channel.findall("item") if channel is not None else []
                last_pubdate_datetime = pubDate_to_datetime(rss_props[1])
                filteredItems = filter(
                    lambda item: pubDate_to_datetime(item.findtext("pubDate", ""))
                    >= last_pubdate_datetime,
                    items,
                )
                sortedFilteredItems = sorted(
                    filteredItems,
                    key=lambda item: pubDate_to_datetime(item.findtext("pubDate", "")),
                )

                if sortedFilteredItems:
                    last_items = eval(rss_props[2])
                    for item in sortedFilteredItems:
                        item_guid = item.findtext("guid", "")
                        if item_guid not in last_items:
                            last_items.append(item_guid)
                            await jackettitem_to_telegram(context, item, rss_name)

                    itemsCount = len(items)
                    while len(last_items) > itemsCount:
                        last_items.pop(0)

                    new_pubdate = sortedFilteredItems[-1].findtext("pubDate", "")
                    sqlite_write(
                        rss_name, rss_props[0], new_pubdate, str(last_items), 0
                    )
        except Exception as exception:
            # If not down yet, put down and send message.
            if rss_props[3] != 1:
                msg = f"Indexer {helpers.escape_markdown(rss_name, 2)} not available due to some issue\."
                await context.bot.send_message(
                    chat_id,
                    f"*ERROR:* {msg}",
                    parse_mode="MARKDOWNV2",
                    message_thread_id=message_thread_id,
                )
                logging.exception(f"{msg}: {exception}")
                sqlite_write(rss_name, rss_props[0], rss_props[1], rss_props[2], 1)
            pass

    rss_load()


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not its_me(update):
        return

    if not context.args or not context.args[0]:
        logging.error(f"User calls command /test with invalid arguments.")
        await telegram_send_reply_error(
            update,
            "The format needs to be:\n`/test JACKETT\_OR\_PROWLARR\_RSS\_FEED\_URL`",
        )
        return

    try:
        response = requests.get(context.args[0])
        root = ElementTree.fromstring(response.content)
        channel = root.find("channel")
        if channel is None:
            return
        title = channel.findtext("title", default="")
        items = channel.findall("item")
    except ElementTree.ParseError:
        await telegram_send_reply_error(
            update,
            "The link does not seem to be a _Jackett or Prowlarr RSS Feed_ or is not supported\.",
        )
        return
    except requests.exceptions.MissingSchema:
        await telegram_send_reply_error(
            update, "The _Jackett or Prowlarr RSS Feed Url_ is malformed\."
        )
        return

    items.sort(
        reverse=True, key=lambda item: pubDate_to_datetime(item.findtext("pubDate", ""))
    )
    await jackettitem_to_telegram(context, items[0], title)


async def jackettitem_to_telegram(
    context: ContextTypes.DEFAULT_TYPE, item: ElementTree.Element, rssName: str
) -> None:
    coverurl = None
    title = helpers.escape_markdown(
        item.findtext("title", default=escaped_backslash), 2
    )
    category = (
        parse_category(item.findtext("category", ""))
        if item.findall("category")
        else -1
    )
    icons = [parse_categoryIcon(category)]
    trackerName = helpers.escape_markdown(rssName, 2)
    externalLinks = []
    seeders = escaped_backslash
    peers = escaped_backslash
    grabs = item.findtext("grabs", default=escaped_backslash)
    files = item.findtext("files", default=escaped_backslash)
    uploadvolumefactor = ""
    downloadvolumefactor = ""
    downloadUrl = ""
    magnetUrl = ""

    size = helpers.escape_markdown(
        str(round(float(item.findtext("size", default=0)) / 1073741824, 2)) + "GiB", 2
    )

    guid = item.findtext("guid", default=None)
    link = item.findtext("link", default=None)
    if guid and guid.startswith("magnet:"):
        magnetUrl = helpers.escape_markdown(guid, 2)
    elif not magnetUrl and link and link.startswith("magnet:"):
        magnetUrl = helpers.escape_markdown(link, 2)
    if link and not link.startswith("magnet:"):
        downloadUrl = link

    keyboard = [[]]
    if item.findall("comments"):
        keyboard[0].append(
            InlineKeyboardButton("🔗", url=item.findtext("comments", default=None))
        )
    if downloadUrl:
        if magnetUrl:
            keyboard[0].append(InlineKeyboardButton("🧲", url=downloadUrl))
        else:
            keyboard[0].append(InlineKeyboardButton("💾", url=downloadUrl))
            keyboard[0].append(InlineKeyboardButton("🕳", callback_data="blackhole"))
    reply_markup = InlineKeyboardMarkup(keyboard)
    ns = {"torznab": "http://torznab.com/schemas/2015/feed"}

    for torznabattr in item.findall("torznab:attr", ns):
        torznabattr_name = torznabattr.get("name")
        if torznabattr_name == "downloadvolumefactor":
            downloadvolumefactor = parse_downloadvolumefactor(
                float(torznabattr.get("value", 0))
            )
            if downloadvolumefactor:
                icons.append(downloadvolumefactor[:1])
        elif torznabattr_name == "uploadvolumefactor":
            uploadvolumefactor = parse_uploadvolumefactor(
                float(torznabattr.get("value", 0))
            )
            if uploadvolumefactor:
                icons.append(uploadvolumefactor[:1])
        elif torznabattr_name == "seeders":
            seeders = torznabattr.get("value")
        elif torznabattr_name == "peers":
            peers = torznabattr.get("value")
        elif torznabattr_name == "coverurl":
            coverurl = torznabattr.get("value")
        elif torznabattr_name == "imdbid":
            externalLinks.append(
                f"[*IMDb*](https://www.imdb.com/title/{torznabattr.get('value')})"
            )
        elif torznabattr_name == "tmdbid":
            type = None
            if category == 2:
                type = "movie"
            elif category == 5:
                type = "tv"
            if type:
                externalLinks.append(
                    f"[*TMDb*](https://www.themoviedb.org/{type}/{torznabattr.get('value')})"
                )
        elif torznabattr_name == "magneturl" and not magnetUrl:
            magnetUrl = torznabattr.get("value")

    externalLinks = ("\n📌 " + "\|".join(externalLinks)) if externalLinks else ""
    message = (
        f"{helpers.escape_markdown('|'.join(icons),2)} \- {title} by _{trackerName}_"
        + f"{externalLinks}"
        + f"\n\n📤 {seeders} 📥 {peers} 💾 {grabs} 🗜 {size} 🗃 {files}"
        + f"\n\n{downloadvolumefactor}{uploadvolumefactor}\n\n`{magnetUrl}`"
    )

    if coverurl:
        try:
            coverraw = requests.get(coverurl, stream=True).raw
            await context.bot.send_photo(
                chat_id,
                photo=coverraw,
                caption=message,
                reply_markup=reply_markup,
                message_thread_id=message_thread_id,
            )
            return
        # Error, most of the times is a Image 400 Bad Request, without reason.
        except:
            logging.warning(
                "Error sending release with cover. Trying to send without cover."
            )

    await context.bot.send_message(
        chat_id, message, reply_markup=reply_markup, message_thread_id=message_thread_id
    )


async def cbq_to_blackhole(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not its_me(update):
        return

    if (
        not (message := update.effective_message)
        or not (reply_markup := message.reply_markup)
        or not (query := update.callback_query)
    ):
        await telegram_send_error(context, "The message cannot be found\.")
        return

    await query.answer()

    inline_keyboard_zero = list(reply_markup.inline_keyboard[0])
    inline_keyboard_zero.pop()
    inline_keyboard_zero.append(InlineKeyboardButton("⏳", callback_data=query.data))

    await context.bot.edit_message_reply_markup(
        chat_id=message.chat_id,
        message_id=message.message_id,
        reply_markup=InlineKeyboardMarkup([inline_keyboard_zero]),
    )

    msg = None
    torrent_url = reply_markup.inline_keyboard[0][1].url
    if torrent_url:
        torrent_file = parse.parse_qs(parse.urlparse(torrent_url).query)["file"][0]
        if torrent_file:
            torrent_file = clean_filename(torrent_file + ".torrent")
            try:
                torrent_data = requests.get(torrent_url)
                if torrent_data and torrent_data.content:
                    button_msg = "✔️"
                    with open(os.path.join(blackhole_path, torrent_file), "wb") as file:
                        file.write(torrent_data.content)
                else:
                    msg = "Can't obtain `.Torrent` file data\."
            except Exception as exception:
                if exception.args[0] and "magnet:?" in exception.args[0]:
                    msg = "It seems that the torrent is a magnet file, it can't be added using blackhole, please use another option\."
                else:
                    logging.exception(exception)
                    msg = "Can't obtain `.Torrent` file data\."
        else:
            msg = "Can't obtain `.Torrent` file name\."
    else:
        msg = "Can't obtain `.Torrent` Url to download\."

    if msg:
        button_msg = "❌"
        await telegram_send_reply_error(update, msg)

    inline_keyboard_zero.pop()
    inline_keyboard_zero.append(
        InlineKeyboardButton(button_msg, callback_data=query.data)
    )

    await context.bot.edit_message_reply_markup(
        chat_id=message.chat_id,
        message_id=message.message_id,
        reply_markup=InlineKeyboardMarkup([inline_keyboard_zero]),
    )


async def post_init(application: Application) -> None:
    msg = (
        "*Jackett2Telegram has started\.*"
        + f"\nRSS Indexers: {str(len(rss_dict))}"
        + f"\nDelay: {str(delay)} seconds"
        + f"\nLog Level: {log_level}"
    )
    clean_msg = msg.replace("\n", "  ")
    logging.info(f"{inspect.stack()[1][3]} - {clean_msg}")
    await application.bot.send_message(
        chat_id, msg, message_thread_id=message_thread_id
    )


# Telegram


async def telegram_send_message(context: ContextTypes.DEFAULT_TYPE, msg: str) -> None:
    clean_msg = msg.replace("\n", "  ")
    logging.info(f"{inspect.stack()[1][3]} - {clean_msg}")
    if bot := context.bot:
        await bot.send_message(
            chat_id, f"*ERROR:* {msg}", message_thread_id=message_thread_id
        )


async def telegram_send_error(context: ContextTypes.DEFAULT_TYPE, msg: str) -> None:
    clean_msg = msg.replace("\n", "  ")
    logging.error(f"{inspect.stack()[1][3]} - {clean_msg}")
    if bot := context.bot:
        await bot.send_message(
            chat_id, f"*ERROR:* {msg}", message_thread_id=message_thread_id
        )


async def telegram_send_reply_text(update: Update, msg: str) -> None:
    clean_msg = msg.replace("\n", "  ")
    logging.info(f"{inspect.stack()[1][3]} - {clean_msg}")
    if message := update.effective_message:
        await message.reply_text(msg)


async def telegram_send_reply_error(update: Update, msg: str) -> None:
    clean_msg = msg.replace("\n", "  ")
    logging.error(f"{inspect.stack()[1][3]} - {clean_msg}")
    if message := update.effective_message:
        await message.reply_text(f"*ERROR:* {msg}")


async def topic_only_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the message is in the desired topic
    desired_topic_id = 123456  # Replace with your topic's ID
    if update.message.message_thread_id == desired_topic_id:
        await update.message.reply_text("This command works in this topic!")
    else:
        await update.message.reply_text("This command is not allowed in this topic.")


def its_me(update: Update) -> bool:
    return str(update.effective_chat.id) == chat_id if update.effective_chat else False


# Utils


def clean_filename(filename: str) -> str:
    # replace spaces
    for r in " ":
        cleaned_filename = filename.replace(r, "_")

    # keep only valid ascii chars
    cleaned_filename = (
        unicodedata.normalize("NFKD", cleaned_filename)
        .encode("ASCII", "ignore")
        .decode()
    )

    # keep only whitelisted chars
    whitelist = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleaned_filename = "".join(c for c in cleaned_filename if c in whitelist)
    if len(cleaned_filename) > char_limit:
        logging.warning(
            f"Filename truncated because it was over {char_limit}. Filenames may no longer be unique."
        )
    return cleaned_filename[:char_limit]


def pubDate_to_datetime(pubDate: str) -> datetime:
    return datetime.strptime(pubDate, "%a, %d %b %Y %H:%M:%S %z")


def parse_downloadvolumefactor(value: float) -> str:
    if value == 0:
        return "🔥 FREELEECH 🔥\n"
    elif value == 0.5:
        return "🌟 50% DOWNLOAD 🌟\n"
    return ""


def parse_uploadvolumefactor(value: float) -> str:
    if value > 1:
        return f"💎 {str(int(value*100))}% UPLOAD 💎"
    return ""


def parse_category(category: str) -> int:
    try:
        value = int(category) // 1000
    except ValueError:
        value = -1
        logging.exception(f"Category: {category} is not an Integer")
    return value


def parse_categoryIcon(category: int) -> str:
    if category == 1:
        return "🎮"
    elif category == 2:
        return "🎬"
    elif category == 3:
        return "🎵"
    elif category == 4:
        return "💾"
    elif category == 5:
        return "📺"
    elif category == 6:
        return "🔶"
    elif category == 7:
        return "📕"
    elif category == 8:
        return "❓"
    return ""


# Main


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        dest="token",
        type=str,
        help="Telegram Bot's unique authentication token.",
        required=True,
    )
    parser.add_argument(
        "--chat_id",
        dest="chat_id",
        type=str,
        help="Unique identifier for the target chat or username of the target channel (in the format @channelusername); for supergroups, use the unique identifier.",
        required=True,
    )
    parser.add_argument(
        "--message_thread_id",
        dest="message_thread_id",
        type=int,
        help="Unique identifier for the target message thread (topic) of the forum; for forum supergroups only.",
        default=None,
    )
    parser.add_argument(
        "--delay",
        dest="delay",
        type=int,
        help="Seconds between each RSS fetching",
        default=600,
    )
    parser.add_argument(
        "--log_level",
        dest="log_level",
        help="Set the level of console logs",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        default=logging.getLevelName(logging.INFO),
    )
    args = parser.parse_args()

    global chat_id
    global message_thread_id
    global delay
    global log_level

    chat_id = args.chat_id
    message_thread_id = args.message_thread_id
    delay = args.delay
    log_level = args.log_level

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=log_level
    )

    defaults = Defaults(
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        do_quote=True,
        parse_mode="MARKDOWNV2",
    )
    application = (
        Application.builder()
        .token(args.token)
        .defaults(defaults)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("add", cmd_rss_add, filters=topic_filter))
    application.add_handler(CommandHandler("help", cmd_help, filters=topic_filter))
    application.add_handler(CommandHandler("test", cmd_test, filters=topic_filter))
    application.add_handler(CommandHandler("list", cmd_rss_list, filters=topic_filter))
    application.add_handler(
        CommandHandler("remove", cmd_rss_remove, filters=topic_filter)
    )
    application.add_handler(CallbackQueryHandler(cbq_to_blackhole))

    # Try to create a database if missing
    try:
        init_sqlite()
    except sqlite3.OperationalError:
        logging.exception("Fail trying to create the Database.")
        pass

    rss_load()

    if job_queue := application.job_queue:
        job_queue.run_repeating(rss_monitor, delay)

    application.run_polling(allowed_updates=Update.ALL_TYPES)
    conn.close()


if __name__ == "__main__":
    main()
