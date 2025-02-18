import os
import boto3
import cv2
import json
from uuid import uuid4
import numpy as np
import ydb
from ydb.iam import MetadataUrlCredentials

ACCESS_KEY = os.getenv('ACCESS_KEY')
SECRET_KEY = os.getenv("SECRET_KEY")
YDB_ENDPOINT = os.getenv('YDB_ENDPOINT')
YDB_DATABASE = os.getenv('YDB_DATABASE')
BUCKET_PHOTOS = os.getenv("BUCKET_PHOTOS")
BUCKET_FACES = os.getenv("BUCKET_FACES")

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


def handler(event, context):
    global driver, session, s3
    driver, session = init_ydb()
    s3 = get_s3_client()

    if isinstance(event, str):
        event = json.loads(event)

    print(json.dumps(event))

    try:
        # Получение задания из очереди
        for message in event['messages']:
            task = json.loads(message['details']['message']['body'])
            original_key = task['original_key']
            face_coords = task['face_coordinates']

            # Загрузка оригинальной фотографии
            response = s3.get_object(Bucket=BUCKET_PHOTOS, Key=original_key)
            image_data = response['Body'].read()

            # Преобразование изображения
            image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)

            # Вырезание лица
            x, y, w, h = face_coords['x'], face_coords['y'], face_coords['width'], face_coords['height']
            face = image[y:y + h, x:x + w]

            # Сохранение лица в бакет
            face_key = f"{uuid4()}.jpg"
            _, buffer = cv2.imencode('.jpg', face)
            s3.put_object(Bucket=BUCKET_FACES,
                          Key=face_key,
                          Body=buffer.tobytes(),
                          ContentType="image/jpeg")

            # Сохранение информации о лице в YDB
            save_face_info(face_key, original_key)
    except Exception as e:
        print(f"Ошибка обработки сообщения: {e}")

    return {
        'statusCode': 200,
        'body': 'Faces cut and saved.'
    }


def save_face_info(face_key, original_key):
    query = f"""
    INSERT INTO photos (face_id, image_id, face_name)
    VALUES ("{face_key}", "{original_key}", NULL);
    """
    session.transaction().execute(query, commit_tx=True)
