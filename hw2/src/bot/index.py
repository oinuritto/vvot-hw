import json
import os
import boto3
import requests
import ydb
from telegram import Update, Bot, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from ydb.iam import MetadataUrlCredentials

ACCESS_KEY = os.getenv('ACCESS_KEY')
SECRET_KEY = os.getenv("SECRET_KEY")
YDB_ENDPOINT = os.getenv('YDB_ENDPOINT')
YDB_DATABASE = os.getenv('YDB_DATABASE')
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL")
BUCKET_PHOTOS = os.getenv("BUCKET_PHOTOS")


bot = None
s3 = None
driver = None
session = None


def get_s3_client():
    global s3
    if s3 is not None:
        return s3
    return boto3.client(
        's3',
        endpoint_url='https://storage.yandexcloud.net',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY
    )


def init_ydb():
    global driver, session
    if driver is not None and session is not None:
        return driver, session

    print("DRIVER SESSION NONE")

    credentials = MetadataUrlCredentials()
    driver_config = ydb.DriverConfig(
        endpoint=f"grpcs://{YDB_ENDPOINT}",
        database=YDB_DATABASE,
        credentials=credentials,
    )
    driver = ydb.Driver(driver_config)
    driver.wait(fail_fast=True, timeout=5)
    session = driver.table_client.session().create()
    return driver, session


async def get_face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("GET FACE METHOD")
    face_key = get_unassigned_face()
    print(f"FACE_KEY={face_key}")
    if face_key:
        photo_url = f"https://{API_GATEWAY_URL}/?face={face_key}"
        print(f"Generated PHOTO_URL={photo_url}")
        try:
            # Отправляем фото с caption, содержащим face_key
            await update.message.reply_photo(photo=photo_url, caption=face_key)
        except Exception as e:
            print(f"Ошибка при отправке фото: {e}")
            await update.message.reply_text("Не удалось загрузить фотографию.")
    else:
        await update.message.reply_text("Нет доступных фотографий лиц.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("HANDLING TEXT")
    # Проверяем, является ли сообщение ответом на фото
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        # Получаем caption из исходного сообщения (это будет face_key)
        face_key = update.message.reply_to_message.caption
        if face_key:
            face_name = update.message.text.strip()  # Имя лица из текста сообщения
            save_face_name(face_key, face_name)
            await update.message.reply_text(f"Имя '{face_name}' успешно сохранено для этого лица.")
        else:
            await update.message.reply_text("Ошибка: не найден ключ лица в исходном сообщении.")
    else:
        await update.message.reply_text("Ошибка.")


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("FIND METHOD")
    name = context.args[0] if context.args else ""
    if not name:
        await update.message.reply_text("Укажите имя для поиска.")
        return

    # Получаем ключи оригинальных фотографий из YDB
    original_photo_keys = get_original_photos_by_name(name)
    if not original_photo_keys:
        await update.message.reply_text(f"Фотографии с {name} не найдены.")
        return

    # Формируем медиагруппу
    media_group = []
    for photo_key in original_photo_keys:
        # Формируем URL для оригинальной фотографии
        photo_url = f"https://{API_GATEWAY_URL}/photo/?photo={photo_key}"
        media_group.append(InputMediaPhoto(media=photo_url))

    # Отправляем медиагруппу
    try:
        await update.message.reply_media_group(media=media_group)
    except Exception as e:
        print(f"Ошибка при отправке медиагруппы: {e}")
        await update.message.reply_text("Не удалось загрузить фотографии.")


async def handler(event, context):
    global bot
    global driver, session, s3
    try:
        driver, session = init_ydb()
        s3 = get_s3_client()
        if not event.get('body'):
            return {'statusCode': 400, 'body': 'Bad Request: No body provided'}
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            return {'statusCode': 400, 'body': 'Bad Request: Invalid JSON'}

        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("getface", get_face))
        app.add_handler(CommandHandler("find", find))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        bot = app.bot
        await bot.initialize()
        await app.initialize()
        await app.process_update(Update.de_json(body, bot))
        await app.shutdown()
        return {'statusCode': 200, 'body': 'OK'}
    except Exception as e:
        print(f"Internal Server Error: {e}")
        return {'statusCode': 500, 'body': 'Internal Server Error'}


def get_unassigned_face():
    query = """
    SELECT face_id FROM photos WHERE face_name IS NULL LIMIT 1;
    """
    result = session.transaction().execute(query, commit_tx=True)
    if result[0].rows:
        return result[0].rows[0]['face_id'].decode("utf-8")  # Преобразуем bytes в строку
    return None


def save_face_name(face_key, face_name):
    query = f"""
    UPDATE photos SET face_name = "{face_name}" WHERE face_id = "{face_key}";
    """
    session.transaction().execute(query, commit_tx=True)


def get_original_photos_by_name(name):
    query = f"""
    SELECT image_id FROM photos WHERE face_name = "{name}";
    """
    result = session.transaction().execute(query, commit_tx=True)
    return [row['image_id'].decode("utf-8") for row in result[0].rows]