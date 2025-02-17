import os
import traceback
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
from uvicorn import run
import boto3
import re

config = configparser.ConfigParser()
current_dir = os.path.dirname(os.path.abspath(__file__))
config_file_path = os.path.join(current_dir, 'config.ini') 
config.read(config_file_path)


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
    
if __name__ == '__main__':
    upload_pictures('/mnt/user/code/tgtorss/pictures/ddgksf2021_6578.jpg', 'ddgksf2021_6578.jpg')