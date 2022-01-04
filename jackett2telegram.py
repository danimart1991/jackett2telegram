import logging
import requests
import os
import sqlite3
import string
import unicodedata
import xml.etree.ElementTree as ElementTree
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler, Defaults
from telegram.utils import helpers
from urllib import parse

blackhole_path = os.path.join(os.path.abspath(
    os.path.dirname(__file__)), "blackhole")
config_path = os.path.join(os.path.abspath(
    os.path.dirname(__file__)), "config")
db_path = os.path.join(config_path, "rss.db")
os.makedirs(blackhole_path, exist_ok=True)
os.makedirs(config_path, exist_ok=True)

levels = {
    'critical': logging.CRITICAL,
    'error': logging.ERROR,
    'warn': logging.WARNING,
    'warning': logging.WARNING,
    'info': logging.INFO,
    'debug': logging.DEBUG
}

token = os.environ['TOKEN'] if os.environ.get('TOKEN') else "<YOUR_TOKEN_HERE>"
chatid = os.environ['CHATID'] if os.environ.get(
    'CHATID') else "<YOUR_CHATID_HERE>"
delay = int(os.environ['DELAY']) if os.environ.get('DELAY') else 600
log_level = levels.get(os.environ['LOG_LEVEL'].lower()) if os.environ.get(
    'LOG_LEVEL') else logging.INFO

ns = {'torznab': 'http://torznab.com/schemas/2015/feed'}
rss_dict = {}

valid_filename_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
char_limit = 255

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=log_level)


# SQLITE


def init_sqlite():
    logging.debug("Trying to create the Database")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rss (name text PRIMARY KEY, link text, last_pubdate text, last_items text, is_down integer)''')


def sqlite_connect():
    global conn
    conn = sqlite3.connect(db_path, check_same_thread=False)


def sqlite_load_all():
    sqlite_connect()
    c = conn.cursor()
    c.execute('SELECT * FROM rss')
    rows = c.fetchall()
    conn.close()
    return rows


def sqlite_write(name: str, link: str, last_pubdate: str, last_items: str, is_down: int):
    sqlite_connect()
    c = conn.cursor()
    values = [(name), (link), (last_pubdate), (last_items), (is_down)]
    c.execute(
        '''REPLACE INTO rss (name,link,last_pubdate,last_items,is_down) VALUES(?,?,?,?,?)''', values)
    conn.commit()
    conn.close()

# RSS


def rss_load():
    # if the dict is not empty, empty it.
    if bool(rss_dict):
        rss_dict.clear()
    for row in sqlite_load_all():
        rss_dict[row[0]] = (row[1], row[2], row[3], row[4])


def cmd_rss_list(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return

    indexers = ["*List of Registered Indexers\.*"]
    if bool(rss_dict) is False:
        indexers.append("The database is empty\.")
    else:
        for rss_name, rss_props in rss_dict.items():
            indexers.append(
                "Title: " + helpers.escape_markdown(rss_name, 2) +
                "\nJacket RSS: `" + helpers.escape_markdown(rss_props[0], 2) + "`" +
                "\nLast article from: " + helpers.escape_markdown(rss_props[1], 2) +
                "\nStatus: " + ("✔️" if rss_props[3] == 0 else "⚠"))

    update.effective_message.reply_markdown_v2("\n\n".join(indexers))


def cmd_rss_add(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    # try if there are 2 arguments passed
    try:
        context.args[1]
    except IndexError:
        telegram_send_reply_error(
            update, "To add a new _Jackett RSS_ the command needs to be:\n`/add TITLE JACKETT_RSS_FEED_URL`")
        raise
    # try if the url is a valid Jackett RSS feed
    try:
        response = requests.get(context.args[1])
        root = ElementTree.fromstring(response.content)
        items = root.find('channel').findall('item')
    except ElementTree.ParseError:
        telegram_send_reply_error(
            update, "The link does not seem to be a _Jackett RSS Feed_ or is not supported\.")
        raise
    except requests.exceptions.MissingSchema:
        telegram_send_reply_error(
            update, "The _Jackett RSS Feed Url_ is malformed\.")
        raise

    items.sort(reverse=True, key=lambda item: pubDate_to_datetime(
        item.find('pubDate').text))
    sqlite_write(context.args[0], context.args[1],
                 items[0].find('pubDate').text, str([]), 0)
    rss_load()
    logging.info("List: Indexer " +
                 context.args[0] + " | " + context.args[1] + " added.")
    message = ("*Indexer added to list:* " + helpers.escape_markdown(context.args[0], 2) +
               "\n`" + helpers.escape_markdown(context.args[1], 2) + "`")
    update.effective_message.reply_markdown_v2(message)


def cmd_rss_remove(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    # try if there are 1 arguments passed
    try:
        context.args[0]
    except IndexError:
        telegram_send_reply_error(
            update, "To remove a _Jackett RSS_ the command needs to be:\n`/remove TITLE`")
        raise
    sqlite_connect()
    c = conn.cursor()
    q = (context.args[0],)
    escaped_indexer = helpers.escape_markdown(context.args[0], 2)
    try:
        c.execute("SELECT count(*) FROM rss WHERE name = ?", q)
        res = c.fetchall()[0][0]
        if not (int(res) == 1):
            telegram_send_reply_error(
                update, "Can't remove _Jackett RSS_ with title _" + escaped_indexer + "_\. Not found\.")
            raise KeyError("Indexer with name " +
                           context.args[0] + " not found.")
        c.execute("DELETE FROM rss WHERE name = ?", q)
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        telegram_send_reply_error(
            update, "Can't remove the _Jackett RSS_ because of an unknown issue\.")
        raise
    rss_load()
    logging.info("List: Indexer " + context.args[0] + " removed.")
    message = ("*Indexer removed from list:* " + escaped_indexer)
    update.effective_message.reply_markdown_v2(message)


def cmd_help(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    update.effective_message.reply_markdown_v2(
        "*Jackett2Telegram \(Jackett RSS to Telegram Bot\)*" +
        "\n\nAfter successfully adding a Jackett RSS link, the bot starts fetching the feed every "
        + str(delay) + " seconds\. \(This can be set\)" +
        "\n\nTitles are used to easily manage RSS feeds and should contain only one word and are case sensitive\." +
        "\n\nCommands:" +
        "\n\- /help \- Posts this help message\. 😑" +
        "\n\- /add TITLE JACKETT\_RSS\_FEED\_URL \- Adds new Jackett RSS Feed \(overwrited if title previously exist\)\." +
        "\n\- /remove TITLE \- Removes the RSS link\." +
        "\n\- /list \- Lists all the titles and the asociated Jackett RSS links from the DB\." +
        "\n\- /test JACKETT\_RSS\_FEED\_URL \- Inbuilt command that fetches a post \(usually latest\) from a Jackett RSS\." +
        "\n\nIn order to use *Blackhole*, your _Torrent_ client must support it and be configured to point to *Jackett2Telegram* _Blackhole_ folder\."
        "\n\nIf you like the project, star it on [GitHub](https://github\.com/danimart1991/jackett2telegram)\.")


def rss_monitor(context: CallbackContext):
    for rss_name, rss_props in rss_dict.items():
        try:
            response = requests.get(rss_props[0])
            root = ElementTree.fromstring(response.content)
            items = root.find('channel').findall('item')
            last_pubdate_datetime = pubDate_to_datetime(rss_props[1])
            filteredItems = filter(
                lambda item: pubDate_to_datetime(item.find('pubDate').text) >= last_pubdate_datetime, items)
            sortedFilteredItems = sorted(
                filteredItems, key=lambda item: pubDate_to_datetime(item.find('pubDate').text))

            if sortedFilteredItems:
                last_items = eval(rss_props[2])
                for item in sortedFilteredItems:
                    item_guid = item.find('guid').text
                    if item_guid not in last_items:
                        last_items.append(item_guid)
                        jackettitem_to_telegram(context, item, rss_name)

                itemsCount = len(items)
                while (len(last_items) > itemsCount):
                    last_items.pop(0)

                new_pubdate = sortedFilteredItems[-1].find('pubDate').text
                sqlite_write(rss_name, rss_props[0],
                             new_pubdate, str(last_items), 0)
        except:
            if (rss_props[3] != 1):
                msg = "Indexer not available due to some issue: " + \
                    helpers.escape_markdown(rss_name, 2)
                context.bot.send_message(
                    chatid, "*ERROR:* " + msg, parse_mode="MARKDOWNV2")
                logging.exception(msg)
                sqlite_write(rss_name, rss_props[0],
                             rss_props[1], rss_props[2], 1)
            pass

    rss_load()


def cmd_test(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    # try if there are 1 arguments passed
    try:
        context.args[0]
    except IndexError:
        telegram_send_reply_error(
            update, "The format needs to be:\n`/test JACKETT\_RSS\_FEED\_URL`")
        raise
    # try if the url is a valid Jackett RSS feed
    try:
        response = requests.get(context.args[0])
        root = ElementTree.fromstring(response.content)
        title = root.find('channel').find('title').text
        items = root.find('channel').findall('item')
    except ElementTree.ParseError:
        telegram_send_reply_error(
            update, "The link does not seem to be a _Jackett RSS Feed_ or is not supported\.")
        raise
    except requests.exceptions.MissingSchema:
        telegram_send_reply_error(
            update, "The _Jackett RSS Feed Url_ is malformed\.")
        raise

    items.sort(reverse=True, key=lambda item: pubDate_to_datetime(
        item.find('pubDate').text))
    jackettitem_to_telegram(context, items[0], title)


def pubDate_to_datetime(pubDate: str):
    return datetime.strptime(pubDate, "%a, %d %b %Y %H:%M:%S %z")


def parse_downloadvolumefactor(value: float):
    if (value == 0):
        return "🔥 FREELEECH 🔥\n"
    elif (value == 0.5):
        return "🌟 50% DOWNLOAD 🌟\n"
    return ""


def parse_uploadvolumefactor(value: float):
    if (value > 1):
        return "💎 " + str(int(value*100)) + "% UPLOAD 💎"
    return ""


def parse_typeIcon(value: int):
    type = str(value)[:1]
    if (type == "1"):
        return "🎮"
    elif (type == "2"):
        return "🎬"
    elif (type == "3"):
        return "🎵"
    elif (type == "4"):
        return "💾"
    elif (type == "5"):
        return "📺"
    elif (type == "6"):
        return "🔶"
    elif (type == "7"):
        return "📕"
    elif (type == "8"):
        return "❓"
    return ""


def jackettitem_to_telegram(context: CallbackContext, item: ElementTree.Element, rssName: str):
    coverurl = None
    title = helpers.escape_markdown(item.find('title').text, 2)
    category = item.find('category').text
    icons = [parse_typeIcon(category)]
    trackerName = helpers.escape_markdown(rssName, 2)
    externalLinks = []
    seeders = "\-"
    peers = "\-"
    grabs = item.find('grabs').text if item.find('grabs') else "\-"
    uploadvolumefactor = ""
    downloadvolumefactor = ""
    magnet = ""

    size = helpers.escape_markdown(
        str(round(float(item.find('size').text)/1073741824, 2)) + "GB", 2)

    link = item.find('link').text
    if (link.startswith("magnet:")):
        magnet = helpers.escape_markdown(link, 2)
        keyboard = [
            [
                InlineKeyboardButton("Link", url=item.find('comments').text)
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("Link", url=item.find('comments').text),
                InlineKeyboardButton(".Torrent", url=link)
            ],
            [
                InlineKeyboardButton("To Blackhole", callback_data='blackhole')
            ]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    for torznabattr in item.findall('torznab:attr', ns):
        torznabattr_name = torznabattr.get('name')
        if (torznabattr_name == "downloadvolumefactor"):
            downloadvolumefactor = parse_downloadvolumefactor(
                float(torznabattr.get('value')))
            if downloadvolumefactor:
                icons.append(downloadvolumefactor[:1])
        elif (torznabattr_name == "uploadvolumefactor"):
            uploadvolumefactor = parse_uploadvolumefactor(
                float(torznabattr.get('value')))
            if uploadvolumefactor:
                icons.append(uploadvolumefactor[:1])
        elif (torznabattr_name == "seeders"):
            seeders = torznabattr.get('value')
        elif (torznabattr_name == "peers"):
            peers = torznabattr.get('value')
        elif (torznabattr_name == "coverurl"):
            basecoverurl = torznabattr.get('value')
            if (basecoverurl):
                if (basecoverurl.find("images.weserv.nl") != -1):
                    coverurl = '&'.join(basecoverurl.split('&')[
                                        :-1]) + "&w=180&h=270"
                else:
                    coverurl = "https://images.weserv.nl/?url=" + basecoverurl + "&w=180&h=270"
        elif (torznabattr_name == "imdbid"):
            externalLinks.append(
                "[*IMDb*](https://www.imdb.com/title/" + torznabattr.get('value') + ")")
        elif (torznabattr_name == "tmdbid"):
            type = None
            if str(category)[:1] == "2":
                type = "movie"
            elif str(category)[:1] == "5":
                type = "tv"
            if type:
                externalLinks.append(
                    "[*TMDb*](https://www.themoviedb.org/" + type + "/" + torznabattr.get('value') + ")")

    message = ("\|".join(icons) + " \- " + title + " by _" + trackerName + "_" +
               ("\n📌 " + "\|".join(externalLinks) if externalLinks else "") +
               "\n\n" +
               "📤 " + seeders + " 📥 " + peers + " 💾 " + grabs + " 🗜 " + size +
               "\n\n" +
               downloadvolumefactor +
               uploadvolumefactor +
               "\n`" + magnet + "`")

    if coverurl:
        try:
            context.bot.send_photo(chatid, coverurl, message,
                                   reply_markup=reply_markup, parse_mode="MARKDOWNV2")
            return
        # Error, most of the times is a Image 400 Bad Request, without reason.
        except:
            pass

    context.bot.send_message(
        chatid, message, reply_markup=reply_markup, parse_mode="MARKDOWNV2")

# Telegram


def telegram_send_reply_error(update: Update, msg: str):
    update.effective_message.reply_markdown_v2("*ERROR:* " + msg, quote=True)


def its_me(update: Update):
    return str(update.effective_chat.id) == chatid


# Utils


def cbq_to_blackhole(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return

    query = update.callback_query
    try:
        query.answer()
    except:
        pass

    keyboard = [
        update.effective_message.reply_markup.inline_keyboard[0],
        [
            InlineKeyboardButton("🕑", callback_data='blackhole')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.edit_message_reply_markup(
        chat_id=update.effective_message.chat_id,
        message_id=update.effective_message.message_id,
        reply_markup=reply_markup)

    msg = None
    torrent_url = update.effective_message.reply_markup.inline_keyboard[0][1].url
    if (torrent_url):
        torrent_file = parse.parse_qs(
            parse.urlparse(torrent_url).query)['file'][0]
        if (torrent_file):
            torrent_file = clean_filename(torrent_file + ".torrent")
            torrent_data = requests.get(torrent_url)
            if torrent_data and torrent_data.content:
                button_msg = "Downloaded ✔️"
                with open(os.path.join(blackhole_path, torrent_file), 'wb') as file:
                    file.write(torrent_data.content)
            else:
                msg = "Can\'t obtain `.Torrent` file data\."
        else:
            msg = "Can\'t obtain `.Torrent` file name\."
    else:
        msg = "Can\'t obtain `.Torrent` Url to download\."

    if msg:
        button_msg = "Failed ❌"
        telegram_send_reply_error(update, msg)
        logging.error("Blackhole - " + msg)

    keyboard = [
        update.effective_message.reply_markup.inline_keyboard[0],
        [
            InlineKeyboardButton(button_msg, callback_data='blackhole')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.edit_message_reply_markup(
        chat_id=update.effective_message.chat_id,
        message_id=update.effective_message.message_id,
        reply_markup=reply_markup)


def clean_filename(filename, whitelist=valid_filename_chars, replace=' '):
    # replace spaces
    for r in replace:
        filename = filename.replace(r, '_')

    # keep only valid ascii chars
    cleaned_filename = unicodedata.normalize(
        'NFKD', filename).encode('ASCII', 'ignore').decode()

    # keep only whitelisted chars
    cleaned_filename = ''.join(c for c in cleaned_filename if c in whitelist)
    if len(cleaned_filename) > char_limit:
        logging.warning(
            "Filename truncated because it was over {}. Filenames may no longer be unique.".format(char_limit))
    return cleaned_filename[:char_limit]

# Main


def main():
    updater = Updater(token=token, use_context=True)
    job_queue = updater.job_queue
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("add", cmd_rss_add))
    dp.add_handler(CommandHandler("help", cmd_help))
    dp.add_handler(CommandHandler("test", cmd_test, ))
    dp.add_handler(CommandHandler("list", cmd_rss_list))
    dp.add_handler(CommandHandler("remove", cmd_rss_remove))
    dp.add_handler(CallbackQueryHandler(cbq_to_blackhole))

    updater.bot.defaults = Defaults(
        disable_web_page_preview=True,
        quote=True,
        parse_mode="MARKDOWNV2")

    # Try to create a database if missing
    try:
        init_sqlite()
    except sqlite3.OperationalError:
        logging.exception("Fail trying to create the Database.")
        pass
    rss_load()

    welcome_message = ("*Jackett2Telegram has started\.*" +
                       "\nRSS Indexers: " + str(len(rss_dict)) +
                       "\nDelay: " + str(delay) + " seconds" +
                       "\nLog Level: " + logging.getLevelName(log_level))
    updater.bot.send_message(
        chatid, welcome_message, parse_mode="MARKDOWNV2")

    job_queue.run_repeating(rss_monitor, delay)

    updater.start_polling()
    updater.idle()
    conn.close()


if __name__ == '__main__':
    main()
