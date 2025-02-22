import os
import traceback
from fastapi import FastAPI, HTTPException, Request
from starlette.responses import Response
from telethon.sync import TelegramClient
from telethon import functions
from markdown2 import markdown
import configparser
import pickle
import logging
from feedgen.feed import FeedGenerator
from telethon.tl.types import InputPeerChannel, MessageMediaPhoto, MessageMediaDocument
from uvicorn import run
import boto3
import re
import uvicorn


# 读取 config
config = configparser.ConfigParser()
current_dir = os.path.dirname(os.path.abspath(__file__))
config_file_path = os.path.join(current_dir, 'config.ini') 
log_file_path = os.path.join(current_dir, "tg2rss.log") 
config.read(config_file_path)

# 配置日志记录
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     handlers=[
#         logging.FileHandler(log_file_path),
#         # logging.StreamHandler()
#     ]
# )

# logger = logging.getLogger(__name__)

app = FastAPI()

block_list = ["证书", "机场", "流量卡", "游戏", "运营商", "星链云", "Hneko", "伪装上架观影", "香烟", "印度药", "高价收普卡","支付宝每日都可搜索","广告投放","夜煞云","频道推荐"]
replace_list = ["脚本 #QuantumultX #Loon #Surge #Shadowrocket #Stash #Crack"]

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
        logging.error(f"上传失败：{e}")
        return False


async def parse_photo_document(client, messages, channel_name):
    message_photo_content = ""
    for message in messages:
        if message.media and (isinstance(message.media, MessageMediaPhoto) or isinstance(message.media, MessageMediaDocument)):
            try:
                file_name = "{}_{}.jpg".format(channel_name, str(message.id))
                file_path = "{}/pictures/{}".format(os.getcwd(), file_name)
                if os.path.exists(file_path):
                    picture_url = config['PICTURES']['END_POINT'] + "/" + config['PICTURES']['BUCKET_NAME'] + "/" + file_name
                else:
                    await client.download_media(message, thumb=-1, file=file_path)
                    picture_url = upload_pictures(file_path, file_name)

                if isinstance(message.media, MessageMediaDocument):
                    documents = message.media.document.attributes
                    message_photo_content += "\n监测到文档: "
                    message_photo_content += ";".join([i.file_name for i in documents])
                    message_photo_content += "\n"
                message_photo_content += f'<img src="{picture_url}" alt="Image">'
            except Exception as e:
                print(e)
                continue
    return message_photo_content


@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/channels/")
async def channels(channel: str):
    try:
        print(channel)

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
                message_id = []
                async for message in client.iter_messages(ch['username']):
                    if message_count < 0:
                        break
                    if message.id in message_id:
                        # 可能group_id中处理过这个message了
                        continue
                    message_id.append(message.id)

                    message_group = [message]
                    message_group_text = str(markdown(message.text)) if message.text else ""
                    # for item in replace_list:
                    #     message_group_text = message_group_text.replace(item, "")
                    
                    # 将普通网址设置为可跳转
                    message_group_text = re.sub(r'<p>(https?://\S+)</p>', r'<a href="\1">\1</a>', message_group_text)
                    if message.grouped_id:
                        group_flag = True
                        curr_id = message.id
                        while True:
                            next_message = await client.get_messages(ch['username'], ids=curr_id - 1)
                            if next_message and next_message.grouped_id and next_message.grouped_id == message.grouped_id:
                                message_group.append(next_message)
                                message_id.append(next_message.id)
                                message_group_text += str(markdown(next_message.text))
                                curr_id -= 1
                            else:
                                break
                    if message_group_text and any(item in message_group_text for item in block_list):
                        continue

                    message_photo_content = await parse_photo_document(client, message_group, ch['username'])

                    # print(message.id, message.text)
                    if message_group_text != "" or message_photo_content != "":
                        fe = fg.add_entry(order='append')
                        title_content = markdown(message.text).strip().splitlines()[0]
                        for item in replace_list:
                            if item in title_content:
                                title_content = markdown(message.text).strip().splitlines()[2]
                                break
                            # title_content = title_content.replace(item, "")
                        fe.title(title_content)
                        fe.guid(guid=f"{link}{ch['username']}/{message.id}", permalink=True)
                        fe.content(message_photo_content + message_group_text)
                        fe.published(message.date)
                        fe.link(href='https://t.me/{}/{}'.format(ch['username'], message.id), rel='alternate')
                    message_count -= 1
                return fg.rss_str()

        response = await get_channel_info(channel)
        # print(response)
        return Response(content=response, media_type='application/xml')
    except Exception as e:
        traceback.print_exc()
        warn = f"{str(e)}, request: '{channel}'"
        logging.error(warn)
        return warn
        
        

if __name__ == '__main__':
    run(app, host="0.0.0.0", port=38088)

