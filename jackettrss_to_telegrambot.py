import logging
import requests
import os
import sqlite3
import xml.etree.ElementTree as ElementTree
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.utils import helpers

Path("config").mkdir(parents=True, exist_ok=True)

# Docker env
if os.environ.get('TOKEN'):
    Token = os.environ['TOKEN']
    chatid = os.environ['CHATID']
    delay = int(os.environ['DELAY'])
else:
    Token = "X"
    chatid = "X"
    delay = 60

if Token == "X":
    print("Token not set!")

ns = {'torznab': 'http://torznab.com/schemas/2015/feed'}
rss_dict = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

# Telegram


def its_me(update: Update):
    return str(update.message.chat.id) == chatid

# SQLITE


def init_sqlite():
    conn = sqlite3.connect('config/rss.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rss (name text PRIMARY KEY, link text, last_pubdate text, last_items text)''')


def sqlite_connect():
    global conn
    conn = sqlite3.connect('config/rss.db', check_same_thread=False)


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
        update.effective_message.reply_text("The database is empty")
    else:
        for title, url_list in rss_dict.items():
            update.effective_message.reply_text(
                "Title: " + title +
                "\nJacket RSS url: " + url_list[0] +
                "\nLast checked article published date: " + url_list[1])


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
        "added \nTITLE: %s\nRSS: %s" % (context.args[0], context.args[1]))


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
            update.effective_message.reply_text("ERROR: Jackett RSS not found.")
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
        "*Jackett RSS to Telegram bot*" +
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
        "\n\nIf you like the project, star it on [DockerHub]\(https://hub\.docker\.com/r/danimart1991/jackettrss\-to\-telegrambot\)\.")


def rss_monitor(context: CallbackContext):
    for name, url_list in rss_dict.items():
        response = requests.get(url_list[0])
        root = ElementTree.fromstring(response.content)
        items = root.find('channel').findall('item')
        items.sort(reverse=True, key=lambda item: pubDate_to_datetime(
            item.find('pubDate').text))
        new_pubdate = items[0].find('pubDate').text
        new_pubdate_date = pubDate_to_date(new_pubdate)
        filteredItems = filter(lambda item: pubDate_to_date(
            item.find('pubDate').text) == new_pubdate_date, items)

        last_pubdate_date = pubDate_to_date(url_list[1])
        if (last_pubdate_date > new_pubdate_date):
            return

        last_items = []
        if (last_pubdate_date == new_pubdate_date):
            last_items = eval(url_list[2])

        for item in filteredItems:
            item_guid = item.find('guid').text
            if item_guid not in last_items:
                jackettitem_to_telegram(context, item, name)
                last_items.append(item_guid)

        sqlite_write((name), (url_list[0]), (new_pubdate), (str(last_items)))
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


def pubDate_to_date(pubDate: str):
    return pubDate_to_datetime(pubDate).date()


def parse_downloadvolumefactor(value: float):
    if (value == 0):
        return "🔥 FREELEECH 🔥\n"
    elif (value == 0.5):
        return "⭐️ 50% DL ⭐️\n"
    return ""


def parse_uploadvolumefactor(value: float):
    if (value > 1):
        return "💎 " + str(int(value*100)) + "% UL 💎"
    return ""


def parse_type(value: int):
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
    uploadvolumefactor = ""
    downloadvolumefactor = ""
    seeders = "\-"
    peers = "\-"
    grabs = item.find('grabs').text if item.find('grabs') else "\-"
    title = helpers.escape_markdown(item.find('title').text, 2)
    type = parse_type(item.find('category').text)
    trackerName = helpers.escape_markdown(
        rssName or item.find('jackettindexer').text, 2)
    size = helpers.escape_markdown(
        str(round(float(item.find('size').text)/1073741824, 2)) + "GB", 2)

    for torznabattr in item.findall('torznab:attr', ns):
        torznabattr_name = torznabattr.get('name')
        if (torznabattr_name == "downloadvolumefactor"):
            downloadvolumefactor = parse_downloadvolumefactor(
                float(torznabattr.get('value')))
        elif (torznabattr_name == "uploadvolumefactor"):
            uploadvolumefactor = parse_uploadvolumefactor(
                float(torznabattr.get('value')))
        elif (torznabattr_name == "seeders"):
            seeders = torznabattr.get('value')
        elif (torznabattr_name == "peers"):
            peers = torznabattr.get('value')
        elif (torznabattr_name == "coverurl"):
            coverurl = torznabattr.get('value').split('&')[0]

    icondownloadvolumefactor = "\|" + \
        downloadvolumefactor[:1] if len(downloadvolumefactor[:1]) == 1 else ""
    iconuploadvolumefactor = "\|" + \
        uploadvolumefactor[:1] if len(uploadvolumefactor[:1]) == 1 else ""

    message = (type + icondownloadvolumefactor + iconuploadvolumefactor + ' \- *' + title + "* by " + trackerName +
               "\n\n" +
               "⬆ " + seeders + " ⬇ " + peers + " 💾 " + grabs + " 🗜 " + size +
               "\n\n" +
               downloadvolumefactor +
               uploadvolumefactor)

    keyboard = [
        [
            InlineKeyboardButton("Link", url=item.find('guid').text),
            InlineKeyboardButton(".Torrent", url=item.find('link').text)
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if (coverurl):
        context.bot.send_photo(chatid, coverurl, message,
                               reply_markup=reply_markup, parse_mode="MARKDOWNV2")
    else:
        context.bot.send_message(
            chatid, message, reply_markup=reply_markup, parse_mode="MARKDOWNV2")

# Main


def main():
    updater = Updater(token=Token, use_context=True)
    job_queue = updater.job_queue
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("add", cmd_rss_add))
    dp.add_handler(CommandHandler("help", cmd_help))
    dp.add_handler(CommandHandler("test", cmd_test, ))
    dp.add_handler(CommandHandler("list", cmd_rss_list))
    dp.add_handler(CommandHandler("remove", cmd_rss_remove))

    # try to create a database if missing
    try:
        init_sqlite()
    except sqlite3.OperationalError:
        pass
    rss_load()

    job_queue.run_repeating(rss_monitor, delay)

    updater.start_polling()
    updater.idle()
    conn.close()


if __name__ == '__main__':
    main()
