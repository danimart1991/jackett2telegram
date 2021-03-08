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

token = os.environ['TOKEN'] if os.environ.get('TOKEN') else "<YOUR_TOKEN_HERE>"
chatid = os.environ['CHATID'] if os.environ.get('CHATID') else "<YOUR_CHATID_HERE>"
levels = {
    'critical': logging.CRITICAL,
    'error': logging.ERROR,
    'warn': logging.WARNING,
    'warning': logging.WARNING,
    'info': logging.INFO,
    'debug': logging.DEBUG
}

delay = int(os.environ['DELAY']) if os.environ.get('DELAY') else 60
log_level = levels.get(os.environ.get('LOG_LEVEL')) or logging.INFO

ns = {'torznab': 'http://torznab.com/schemas/2015/feed'}
rss_dict = {}

valid_filename_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
char_limit = 255

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=log_level)


# SQLITE


def init_sqlite():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rss (name text PRIMARY KEY, link text, last_pubdate text, last_items text)''')


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


def sqlite_write(name: str, link: str, last_pubdate: str, last_items: str):
    sqlite_connect()
    c = conn.cursor()
    values = [(name), (link), (last_pubdate), (last_items)]
    c.execute(
        '''REPLACE INTO rss (name,link,last_pubdate,last_items) VALUES(?,?,?,?)''', values)
    conn.commit()
    conn.close()

# RSS


def rss_load():
    # if the dict is not empty, empty it.
    if bool(rss_dict):
        rss_dict.clear()
    for row in sqlite_load_all():
        rss_dict[row[0]] = (row[1], row[2], row[3])


def cmd_rss_list(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    if bool(rss_dict) is False:
        update.effective_message.reply_text("The database is empty.")
    else:
        for title, url_list in rss_dict.items():
            message = helpers.escape_markdown(
                "Title: " + title +
                "\nJacket RSS url: " + url_list[0] +
                "\nLast checked article published date: " + url_list[1],
                2)
            update.effective_message.reply_markdown_v2(message)


def cmd_rss_add(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    # try if there are 2 arguments passed
    try:
        context.args[1]
    except IndexError:
        update.effective_message.reply_text(
            "ERROR: The format needs to be: /add title http://www.JACKETTRSSURL.com")
        raise
    # try if the url is a valid Jackett RSS feed
    try:
        response = requests.get(context.args[1])
        root = ElementTree.fromstring(response.content)
        items = root.find('channel').findall('item')
    except ElementTree.ParseError:
        update.effective_message.reply_text(
            "ERROR: The link does not seem to be a Jackett RSS feed or is not supported")
        raise

    items.sort(reverse=True, key=lambda item: pubDate_to_datetime(
        item.find('pubDate').text))
    sqlite_write(context.args[0], context.args[1],
                 items[0].find('pubDate').text, str([]))
    rss_load()
    update.effective_message.reply_text(
        "Added: %s\n%s" % (context.args[0], context.args[1]))


def cmd_rss_remove(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    sqlite_connect()
    c = conn.cursor()
    q = (context.args[0],)
    try:
        c.execute("SELECT count(*) FROM rss WHERE name = ?", q)
        res = c.fetchall()[0][0]
        if not (int(res) == 1):
            update.effective_message.reply_text(
                "ERROR: Jackett RSS not found.")
            return
        c.execute("DELETE FROM rss WHERE name = ?", q)
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        update.effective_message.reply_text(
            "ERROR: Can't remove the Jackett RSS because of an uknown issue.")
        print('Error %s:' % e.args[0])
        raise
    rss_load()
    update.effective_message.reply_text("Removed: " + context.args[0])


def cmd_help(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    update.effective_message.reply_markdown_v2(
        "*Jackett RSS to Telegram Bot*" +
        "\n\nAfter successfully adding a Jackett RSS link, the bot starts fetching the feed every "
        + str(delay) + " seconds\. \(This can be set\)" +
        "\n\nTitles are used to easily manage RSS feeds and need to contain only one word\." +
        "\n\nCommands:" +
        "\n\- `/help` Posts this help message\. 😑" +
        "\n\- `/add title http://www\.JACKETTRSSURL\.com` Adds new Jackett RSS \(overwrited if title previously exist\)\." +
        "\n\- `/remove Title` Removes the RSS link\." +
        "\n\- `/list` Lists all the titles and the Jackett RSS links from the DB\." +
        "\n\- `/test http://www\.JACKETTRSSURL\.com` Inbuilt command that fetches a post \(usually latest\) from a Jackett RSS\." +
        "\n\nThe current chatId is: " + str(update.message.chat.id) + "\." +
        "\n\nIf you like the project, star it on [DockerHub](https://hub\.docker\.com/r/danimart1991/jackett2telegram)\.")


def rss_monitor(context: CallbackContext):
    for name, url_list in rss_dict.items():
        response = requests.get(url_list[0])
        root = ElementTree.fromstring(response.content)
        items = root.find('channel').findall('item')
        last_pubdate_datetime = pubDate_to_datetime(url_list[1])
        filteredItems = filter(
            lambda item: pubDate_to_datetime(item.find('pubDate').text) >= last_pubdate_datetime, items)
        sortedFilteredItems = sorted(
            filteredItems, key=lambda item: pubDate_to_datetime(item.find('pubDate').text))

        if sortedFilteredItems:
            last_items = eval(url_list[2])
            for item in sortedFilteredItems:
                item_guid = item.find('guid').text
                if item_guid not in last_items:
                    last_items.append(item_guid)
                    jackettitem_to_telegram(context, item, name)

            itemsCount = len(items)
            while (len(last_items) > itemsCount):
                last_items.pop(0)

            new_pubdate = sortedFilteredItems[-1].find('pubDate').text
            sqlite_write((name), (url_list[0]),
                         (new_pubdate), (str(last_items)))
            rss_load()


def cmd_test(update: Update, context: CallbackContext):
    if not (its_me(update)):
        return
    # try if there are 1 arguments passed
    try:
        context.args[0]
    except IndexError:
        update.effective_message.reply_text(
            "ERROR: The format needs to be: /test http://www\.JACKETTRSSURL\.com")
        raise
    # try if the url is a valid Jackett RSS feed
    try:
        response = requests.get(context.args[0])
        root = ElementTree.fromstring(response.content)
        items = root.find('channel').findall('item')
    except ElementTree.ParseError:
        update.effective_message.reply_text(
            "ERROR: The link does not seem to be a Jackett RSS feed or is not supported")
        raise

    items.sort(reverse=True, key=lambda item: pubDate_to_datetime(
        item.find('pubDate').text))
    jackettitem_to_telegram(context, items[0])


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


def jackettitem_to_telegram(context: CallbackContext, item: ElementTree.Element, rssName: str = None):
    coverurl = None
    title = helpers.escape_markdown(item.find('title').text, 2)
    category = item.find('category').text
    icons = [parse_typeIcon(category)]
    trackerName = helpers.escape_markdown(
        rssName or item.find('jackettindexer').text, 2)
    externalLinks = []
    seeders = "\-"
    peers = "\-"
    grabs = item.find('grabs').text if item.find('grabs') else "\-"
    uploadvolumefactor = ""
    downloadvolumefactor = ""

    size = helpers.escape_markdown(
        str(round(float(item.find('size').text)/1073741824, 2)) + "GB", 2)

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
               uploadvolumefactor)

    keyboard = [
        [
            InlineKeyboardButton("Link", url=item.find('guid').text),
            InlineKeyboardButton(".Torrent", url=item.find('link').text)
        ],
        [
            InlineKeyboardButton("To Blackhole", callback_data='blackhole')
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

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


# Utils

def its_me(update: Update):
    return str(update.effective_chat.id) == chatid


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

    message = None
    torrent_url = update.effective_message.reply_markup.inline_keyboard[0][1].url
    if (torrent_url):
        torrent_file = parse.parse_qs(
            parse.urlparse(torrent_url).query)['file'][0]
        if (torrent_file):
            torrent_file = clean_filename(torrent_file + ".torrent")
            torrent_data = requests.get(torrent_url)
            if torrent_data and torrent_data.content:
                button_message = "Downloaded ✔️"
                with open(os.path.join(blackhole_path, torrent_file), 'wb') as file:
                    file.write(torrent_data.content)
            else:
                message = "Can\'t obtain \.Torrent file data\."
        else:
            message = "Can\'t obtain \.Torrent file name\."
    else:
        message = "Can\'t obtain \.Torrent url to download\."

    if message:
        button_message = "Failed ❌"
        update.effective_message.reply_text(
            message, quote=True, parse_mode="MARKDOWNV2")

    keyboard = [
        update.effective_message.reply_markup.inline_keyboard[0],
        [
            InlineKeyboardButton(button_message, callback_data='blackhole')
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
        print("Warning, filename truncated because it was over {}. Filenames may no longer be unique".format(char_limit))
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
        disable_web_page_preview = True,
        parse_mode = "MARKDOWNV2")

    # try to create a database if missing
    try:
        init_sqlite()
    except sqlite3.OperationalError:
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
