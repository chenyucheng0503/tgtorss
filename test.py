from fastapi import FastAPI, HTTPException
from starlette.responses import Response
from telethon.sync import TelegramClient
from telethon import functions
from markdown2 import markdown
import configparser
import pickle
import logging
from feedgen.feed import FeedGenerator

config = configparser.ConfigParser()
config.read('config.ini')

app = FastAPI()

# Initialize your Telegram client here
client = TelegramClient(config['Telegram']['SESSION'], int(config['Telegram']['API_ID']), config['Telegram']['API_HASH'])

try:
    with open('hash.pickle', 'rb') as f:
        channel_hash = pickle.load(f)
    logging.info(f'Readed {len(channel_hash)} records from the hash')
except FileNotFoundError:
    channel_hash = dict()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/channels/")
async def channels(channel: str):
    try:
        async def get_channel_info(channel: str):
            async with TelegramClient(config['Telegram']['SESSION'], int(config['Telegram']['API_ID']), config['Telegram']['API_HASH']) as client:
                if channel not in channel_hash:
                    channel_name = await client.get_entity(channel)
                    ch_full = await client(functions.channels.GetFullChannelRequest(channel=channel_name))
                    username = channel_name.username or channel_name.id
                    channel_hash[channel] = {
                        'username': username,
                        'title': channel_name.title,
                        'id': channel_name.id,
                        'about': ch_full.full_chat.about or str(username),
                    }
                    logging.info(f"Adding to the hash '{channel}'")
                    with open('hash.pickle', 'wb') as f:
                        pickle.dump(channel_hash, f)

                ch = channel_hash[channel]

                fg = FeedGenerator()
                fg.title(f"{ch['title']} (@{ch['username']}, id:{ch['id']})")
                fg.subtitle(ch['about'])
                link = f"t.me/s/{ch['username']}"
                fg.link(href=f'https://{link}', rel='alternate')
                fg.generator(config['RSS']['GENERATOR'])

                message_count = int(config['RSS']['RECORDS'])
                print(ch['username'])
                async for message in client.iter_messages(ch['username']):
                    if message_count < 0:
                        break
                    print(message.id, message.text)
                    if not (config['RSS'].getboolean('SKIP_EMPTY') and not message.text):
                        fe = fg.add_entry(order='append')
                        fe.guid(guid=f"{link}{ch['username']}/{message.id}", permalink=True)
                        fe.content(markdown(message.text))
                        fe.published(message.date)
                    message_count -= 1
                return fg.rss_str()

        response = await get_channel_info(channel)
        print(response)
        return Response(content=response, media_type='application/xml')
    except Exception as e:
        warn = f"{str(e)}, request: '{channel}'"
        logging.error(warn)
        return warn

