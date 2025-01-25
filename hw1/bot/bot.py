import base64
import json
import logging
import os
import tempfile

import boto3
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# Переменные окружения
TG_BOT_KEY = os.getenv("TG_BOT_KEY")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YC_BUCKET_NAME = os.getenv("YC_BUCKET_NAME")
YC_FOLDER_ID = os.getenv("YC_FOLDER_ID")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION")

# Константы для сообщений
START_MESSAGE = (
    'Я помогу подготовить ответ на экзаменационный вопрос по дисциплине "Операционные системы".\n'
    'Пришлите мне фотографию с вопросом или наберите его текстом.'
)
PHOTO_LIMIT_MESSAGE = "Я могу обработать только одну фотографию."
UNSUPPORTED_PHOTO_MESSAGE = "Я не могу обработать эту фотографию."
UNSUPPORTED_MESSAGE_TYPE = "Я могу обработать только текстовое сообщение или фотографию."
GPT_ERROR_MESSAGE = "Я не смог подготовить ответ на экзаменационный вопрос."

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = None


# Загрузка инструкции из Yandex Object Storage
def get_gpt_instruction():
    try:
        session = boto3.session.Session(
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_DEFAULT_REGION
        )
        s3 = session.client(service_name='s3', endpoint_url='https://storage.yandexcloud.net')
        get_object_response = s3.get_object(Bucket=YC_BUCKET_NAME, Key="instruction.txt")
        instruction = get_object_response['Body'].read().decode('utf-8')
        return instruction
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла из Yandex Object Storage: {e}")
        return None


# Генерация ответа с помощью YandexGPT
def generate_answer_from_gpt(question_text):
    instruction = get_gpt_instruction()
    if not instruction:
        return "Не удалось загрузить инструкцию для YandexGPT API."

    data = {
        "modelUri": f"gpt://{YC_FOLDER_ID}/yandexgpt/rc",
        "completionOptions": {"temperature": 0.5, "maxTokens": 2000},
        "messages": [
            {"role": "system", "text": instruction},
            {"role": "user", "text": question_text},
        ]
    }

    try:
        response = requests.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={
                "Accept": "application/json",
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
            },
            json=data,
        )

        if response.status_code == 200:
            return response.json().get('result', {}).get('alternatives', [{}])[0].get('message', {})\
                .get('text', GPT_ERROR_MESSAGE)
        else:
            logger.error(f"Ошибка от YandexGPT API: {response.status_code} - {response.text}")
            return GPT_ERROR_MESSAGE
    except Exception as e:
        logger.error(f"Ошибка при запросе к YandexGPT API: {e}")
        return GPT_ERROR_MESSAGE


# Обработка команды /start и /help
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_MESSAGE)


# Обработка текстового сообщения
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question_text = update.message.text
    answer = generate_answer_from_gpt(question_text)
    await update.message.reply_text(answer)


# Обработка фотографии
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, отправлена ли медиагруппа (несколько фотографий)
    if update.message.media_group_id:
        await update.message.reply_text(PHOTO_LIMIT_MESSAGE)
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    with tempfile.NamedTemporaryFile(dir="/tmp", suffix=".jpg", delete=False) as temp_file:
        file_path = temp_file.name
        await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as image_file:
            image_data = image_file.read()

        base64_img = base64.b64encode(image_data).decode("utf-8")
        ocr_request = {
            "mimeType": "JPEG",
            "languageCodes": ["ru"],
            "model": "page",
            "content": base64_img
        }

        response = requests.post(
            "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
            headers={"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"},
            json=ocr_request,
        )

        if response.status_code == 200:
            ocr_text = response.json().get('result', {}).get('textAnnotation', {}).get('fullText', '')
            if ocr_text:
                answer = generate_answer_from_gpt(ocr_text)
                await update.message.reply_text(answer)
            else:
                await update.message.reply_text(UNSUPPORTED_PHOTO_MESSAGE)
        else:
            await update.message.reply_text(UNSUPPORTED_PHOTO_MESSAGE)
    except Exception as e:
        logger.error(f"Ошибка при обработке фотографии: {e}")
        await update.message.reply_text(UNSUPPORTED_PHOTO_MESSAGE)
    finally:
        os.remove(file_path)


# Обработка других типов сообщений
async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(UNSUPPORTED_MESSAGE_TYPE)


# Handler (точка входа)
async def handler(event, context):
    global bot
    try:
        if not event.get('body'):
            return {'statusCode': 400, 'body': 'Bad Request: No body provided'}

        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            return {'statusCode': 400, 'body': 'Bad Request: Invalid JSON'}

        app = ApplicationBuilder().token(TG_BOT_KEY).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.ALL, handle_other))

        bot = app.bot
        await bot.initialize()

        await app.initialize()
        await app.process_update(Update.de_json(body, bot))
        await app.shutdown()

        return {'statusCode': 200, 'body': 'OK'}
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        return {'statusCode': 500, 'body': 'Internal Server Error'}
