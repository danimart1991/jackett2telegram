![Jackett RSS to Telegram Bot logo](https://github.com/danimart1991/jackett2telegram/blob/main/docs/images/logo.png?raw=true)

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/danimart1991/jackett2telegram)](https://github.com/danimart1991/jackett2telegram/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/danimart1991/jackett2telegram/deploy.yml)](https://github.com/danimart1991/jackett2telegram/actions/workflows/deploy.yml)
[![License](https://img.shields.io/github/license/danimart1991/jackett2telegram)](https://github.com/danimart1991/jackett2telegram/blob/main/LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/danimart1991/jackett2telegram)](https://hub.docker.com/r/danimart1991/jackett2telegram)

[![Tip Me via PayPal](https://img.shields.io/badge/PayPal-tip%20me-blue?logo=paypal&style=flat)](https://www.paypal.me/danimart1991)
[![Sponsor Me via GitHub](https://img.shields.io/badge/GitHub-sponsor%20me-blue?logo=github&style=flat)](https://github.com/sponsors/danimart1991)

# Jackett RSS to Telegram Bot

A **self-hosted Telegram Python Bot** that dumps posts from **Jackett RSS feeds to a Telegram** chat. Based on [**RSS to Telegram bot**](https://github.com/BoKKeR/RSS-to-Telegram-Bot) by [_BoKKeR_](https://github.com/BoKKeR) (Thanks for your effort).

![Image of the chat](https://github.com/danimart1991/jackett2telegram/blob/main/docs/images/example.png?raw=true)

## Requirements

A Telegram Bot is needed that the script will connect to.

You could use [this post](https://www.danielmartingonzalez.com/en/home-assistant-notifications-on-telegram/) to create your own with the [BotFather Telegram Bot](https://telegram.me/botfather).

> Warning! Without chatID the bot wont be able to send automated messages and will only be able to respond to messages.

## Docker Installation

```bash
$ docker create \
  --name=jackett2telegram \
  -e DELAY=600 \
  -e TOKEN=<your_telegram_bot_token> \
  -e CHATID=<your_telegram_bot_chatid> \
  -v </path/to/host/config>:/app/config \
  -v </path/to/host/blackhole>:/app/blackhole \
  --restart unless-stopped \
  danimart1991/jackett2telegram
```

You could include `-e LOG_LEVEL=<log_level>` where `<log_level>` must be _critical_, _error_, _warning_, _info_ (default) or _debug_.

## Manual Installation

Python 3.X

1. Clone the script
2. Install depedencies with:

   ```bash
   pip install -r requirements.txt
   ```

3. Replace your `ChatID` and `Token` on the top of the script.
4. Edit the delay (seconds).
5. Run the script with:

   ```bash
   python jackett2telegram.py
   ```

## Usage

Send `/help` command to the bot to get this message:

> **Jackett2Telegram (Jackett RSS to Telegram Bot)**
>
> After successfully adding a Jackett RSS link, the bot starts fetching the feed every 600 seconds. (This can be set)
>
> Titles are used to easily manage RSS feeds and should contain only one word and are case sensitive.
>
> Commands:
>
> - /help Posts this help message. 😑
> - /add TITLE JACKETT_RSS_FEED_URL - Adds new Jackett RSS Feed (overwrited if title previously exist).
> - /remove TITLE - Removes the RSS link.
> - /list Lists all the titles and the asociated Jackett RSS links from the DB.
> - /test JACKETT_RSS_FEED_URL - Inbuilt command that fetches a post (usually latest) from a Jackett RSS.
>
> In order to use **Blackhole**, your _Torrent_ client must support it and be configured to point to **Jackett2Telegram** _Blackhole_ folder.
>
> If you like the project, star it on [GitHub](https://github.com/danimart1991/jackett2telegram).

### How to add a new Indexer

You could get the **Jackett RSS Feed Url** using the action button in Indexers list:

![Jackett RSS Feed Button](https://github.com/danimart1991/jackett2telegram/blob/main/docs/images/rssfeed.png?raw=true)

Then paste the Url in the chat like `/add AnyTitle Pasted_RSSFeedURL` and send the message. The bot will reply with the result.

### How to use Blackhole

**Blackhole** folder is a monitored folder that your _Torrent_ client checks to look for `.torrent` files and then download them automatically.

First, you must read the documentation of the _Torrent_ client to make sure is supported and simply configure it to point to the blackhole folder created by **Jackett2Telegram**.

When a new release is showed in Telegram, a Blackhole button could be pressed and download the `.torrent` file locally, then _Torrent_ client use it.

> If you use the _Docker_ installation, make a bind between folders.
