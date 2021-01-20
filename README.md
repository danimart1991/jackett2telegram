![Jackett RSS to Telegram Bot logo](https://github.com/danimart1991/jackett2telegram/blob/main/docs/images/logo.png?raw=true)

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/danimart1991/jackett2telegram)](https://github.com/danimart1991/jackett2telegram/releases)
[![GitHub last commit](https://img.shields.io/github/last-commit/danimart1991/jackett2telegram)](https://github.com/danimart1991/jackett2telegram/commits)
[![License](https://img.shields.io/github/license/danimart1991/jackett2telegram)](https://github.com/danimart1991/jackett2telegram/blob/main/LICENSE)

[![Docker Cloud Build](https://img.shields.io/docker/cloud/build/danimart1991/jackett2telegram)](https://hub.docker.com/r/danimart1991/jackett2telegram)
[![Docker Pulls](https://img.shields.io/docker/pulls/danimart1991/jackett2telegram)](https://hub.docker.com/r/danimart1991/jackett2telegram)
[![Docker Stars](https://img.shields.io/docker/stars/danimart1991/jackett2telegram)](https://hub.docker.com/r/danimart1991/jackett2telegram)

[![Tip Me via PayPal](https://img.shields.io/badge/PayPal-tip%20me-blue?logo=paypal&style=flat)](https://www.paypal.me/danimart1991)
[![Sponsor Me via GitHub](https://img.shields.io/badge/GitHub-sponsor%20me-blue?logo=github&style=flat)](https://github.com/sponsors/danimart1991)

# Jackett RSS to Telegram Bot

A **self-hosted Telegram Python Bot** that dumps posts from **Jackett RSS feeds to a Telegram** chat. Based on [**RSS to Telegram bot**](https://github.com/BoKKeR/RSS-to-Telegram-Bot) by [_BoKKeR_](https://github.com/BoKKeR) (Thanks for your effort).

![Image of the chat](https://github.com/danimart1991/jackett2telegram/blob/main/docs/images/example.png?raw=true)

## Requirements

A Telegram Bot is needed that the script will connect to.

You could use [this post](https://www.danielmartingonzalez.com/en/home-assistant-notifications-on-telegram/) to create your own with the [BotFather Telegram Bot](https://telegram.me/botfather).

Warning! Without chatID the bot wont be able to send automated messages and will only be able to respond to messages.

## Docker Installation

```bash
$ docker create \
  --name=jackett2telegram \
  -e DELAY=60 \
  -e TOKEN=TelegramBotToken \
  -e CHATID=TelegramBotChatID \
  -v /path/to/host/config:/app/config \
  --restart unless-stopped \
  danimart1991/jackett2telegram
```

## Manual Installation

Python 3.X

1. Clone the script
2. Install depedencies with:

    ```bash
    pip install -r requirements.txt
    ```

3. Replace your ChatID and Token on the top of the script.
4. Edit the delay (seconds).
5. Run the script with:

    ```bash
    python jackett2telegram.py
    ```

## Usage

Send `/help` to the bot to get this message:

> Jackett RSS to Telegram bot
>
> After successfully adding a Jackett RSS link, the bot starts fetching the feed every 60 seconds. (This can be set)
>
> Titles are used to easily manage RSS feeds and need to contain only one word.
>
> Commands:
>
> - /help Posts this help message. 😑
> - /add title http://www.JACKETTRSSURL.com Adds new Jackett RSS (overwrited if title previously exist).
> - /remove Title Removes the RSS link.
> - /list Lists all the titles and the Jackett RSS links from the DB.
> - /test http://www.JACKETTRSSURL.com Inbuilt command that fetches a post (usually latest) from a Jackett RSS.
>
> The current chatId is: 123XXXXXXX.
>
> If you like the project, star it on DockerHub(https://hub.docker.com/r/danimart1991/jackett2telegram).

You could get the **Jackett RSS Feed Url** using the action button in Indexers list:

![Jackett RSS Feed Button](https://github.com/danimart1991/jackett2telegram/blob/main/docs/images/rssfeed.png?raw=true)
