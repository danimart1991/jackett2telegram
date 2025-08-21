#!/bin/sh

CMD="python jackett2telegram.py --token ${TOKEN} --chat_id ${CHATID} --delay ${DELAY} --log_level ${LOG_LEVEL}"

if [ -n "${MESSAGE_THREAD_ID}" ]; then
    CMD="${CMD} --message_thread_id ${MESSAGE_THREAD_ID}"
fi

exec ${CMD}