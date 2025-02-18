import json
import os
import boto3
import cv2
import numpy as np

ACCESS_KEY = os.getenv('ACCESS_KEY')
SECRET_KEY = os.getenv("SECRET_KEY")
QUEUE_URL = os.getenv("QUEUE_URL")

s3 = None
sqs = None


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


def get_sqs_client():
    global sqs
    if sqs is not None:
        return sqs

    return boto3.client(
        'sqs',
        endpoint_url='https://message-queue.api.cloud.yandex.net',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name="ru-central1",
    )


# Загрузка классификатора для обнаружения лиц
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')


def handler(event, context):
    global s3, sqs
    s3 = get_s3_client()
    sqs = get_sqs_client()

    if isinstance(event, str):
        event = json.loads(event)

    print(json.dumps(event))

    try:
        # Получение информации о загруженной фотографии
        bucket_name = event['messages'][0]['details']['bucket_id']
        object_key = event['messages'][0]['details']['object_id']

        # Загрузка фотографии
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        image_data = response['Body'].read()

        # Преобразование изображения
        image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Обнаружение лиц
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        for (x, y, w, h) in faces:
            task = {
                "original_key": object_key,
                "face_coordinates": {
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h)
                }
            }
            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(task))
    except Exception as e:
        print(f"Ошибка обработки сообщения: {e}")

    return {
        'statusCode': 200,
        'body': 'Faces detected and tasks sent to queue.'
    }
