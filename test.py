import os

from fastapi import FastAPI, HTTPException
from starlette.responses import Response
from telethon.sync import TelegramClient
from telethon import functions
from markdown2 import markdown
import configparser
import pickle
import logging
from feedgen.feed import FeedGenerator
from telethon.tl.types import InputPeerChannel, MessageMediaPhoto, MessageMediaDocument

import boto3

config = configparser.ConfigParser()
config.read('config.ini')

app = FastAPI()

block_list = ["广告", "证书", "机场", "流量", "游戏", "运营商", "代理", "星链云"]

try:
    with open('hash.pickle', 'rb') as f:
        channel_hash = pickle.load(f)
    logging.info(f'Readed {len(channel_hash)} records from the hash')
except FileNotFoundError:
    channel_hash = dict()


def upload_pictures(file_path, object_name):
    try:
        # 创建 S3 客户端并配置凭证
        s3_client = boto3.client('s3', aws_access_key_id=config['PICTURES']['SECRET_ID'], aws_secret_access_key=config['PICTURES']['SECRET_KEY'], endpoint_url=config['PICTURES']['END_POINT'])

        # 上传文件到 S3 存储桶
        s3_client.upload_file(file_path, config['PICTURES']['BUCKET_NAME'], object_name)

        return config['PICTURES']['END_POINT'] + "/" + config['PICTURES']['BUCKET_NAME'] + "/" + object_name
    except Exception as e:
        print(f"上传失败：{e}")
        return False

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
                fg.title(f"{ch['title']}")
                fg.subtitle(ch['about'])
                link = f"t.me/s/{ch['username']}"
                fg.link(href=f'https://{link}', rel='alternate')
                fg.generator(config['RSS']['GENERATOR'])

                message_count = int(config['RSS']['RECORDS'])
                # print(ch['username'])
                async for message in client.iter_messages(ch['username']):
                    text = message.text
                    if message_count < 0:
                        break
                    if text and any(item in text for item in block_list):
                        continue

                    message_content = ""
                    if message.media and isinstance(message.media, MessageMediaPhoto):
                        photo = message.media.photo
                        file_name = "{}_{}.jpg".format(ch['username'], str(message.id))
                        file_path = "/root/code/tgtorss/pictures/{}".format(file_name)
                        if os.path.exists(file_path):
                            picture_url = config['PICTURES']['END_POINT'] + "/" + config['PICTURES']['BUCKET_NAME'] + "/" + file_name
                        else:
                            await client.download_media(message, thumb=-1, file=file_path)
                            picture_url = upload_pictures(file_path, file_name)

                        message_content += f'<a href="{picture_url}" target="_blank" rel="noopener" onclick="return confirm(\'Open this link? Click OK to open:{picture_url}\');"><img src="{picture_url}" alt="Image"></a>'
                        # message_content += "![{}]({})".format(file_name, picture_url)

                    if isinstance(message.media, MessageMediaDocument):
                        file_name = "{}_{}_thumb.jpg".format(ch['username'], str(message.id))
                        file_path = "/root/code/tgtorss/pictures/{}".format(file_name)
                        if os.path.exists(file_path):
                            picture_url = config['PICTURES']['END_POINT'] + "/" + config['PICTURES']['BUCKET_NAME'] + "/" + file_name
                        else:
                            await client.download_media(message, thumb=-1, file=file_path)
                            picture_url = upload_pictures(file_path, file_name)
                        message_content += f'<a href="{picture_url}" target="_blank" rel="noopener" onclick="return confirm(\'Open this link? Click OK to open:{picture_url}\');"><img src="{picture_url}" alt="Image"></a>'
                        # message_content += "![{}]({})".format(file_name, picture_url)

                    # print(message.id, message.text)
                    if text or message_content != "":
                        message_content += str(markdown(message.text))
                        fe = fg.add_entry(order='append')
                        fe.title(markdown(message.text).strip().splitlines()[0])
                        fe.guid(guid=f"{link}{ch['username']}/{message.id}", permalink=True)
                        fe.content(message_content)
                        fe.published(message.date)
                    message_count -= 1
                return fg.rss_str()

        response = await get_channel_info(channel)
        # print(response)
        return Response(content=response, media_type='application/xml')
    except Exception as e:
        warn = f"{str(e)}, request: '{channel}'"
        logging.error(warn)
        return warn


