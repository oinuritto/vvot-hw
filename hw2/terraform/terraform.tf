terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
  required_version = ">= 0.13"
}

provider "yandex" {
  cloud_id                 = var.cloud_id
  folder_id                = var.folder_id
  service_account_key_file = pathexpand(var.key_file_path)
  zone                     = var.region_name
}

resource "yandex_iam_service_account" "saf_bot_account" {
  name      = var.sa_account
  folder_id = var.folder_id
}

resource "yandex_resourcemanager_folder_iam_member" "editor_role" {
  folder_id = var.folder_id
  role      = "editor"
  member    = "serviceAccount:${yandex_iam_service_account.saf_bot_account.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "queue_role" {
  folder_id = var.folder_id
  role      = "ymq.admin"
  member    = "serviceAccount:${yandex_iam_service_account.saf_bot_account.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "ydb_role" {
  folder_id = var.folder_id
  role      = "ydb.admin"
  member    = "serviceAccount:${yandex_iam_service_account.saf_bot_account.id}"
}

resource "yandex_iam_service_account_static_access_key" "queue_static_key" {
  service_account_id = yandex_iam_service_account.saf_bot_account.id
}

resource "yandex_storage_bucket" "bucket_photos" {
  bucket        = var.photos_bucket
  folder_id     = var.folder_id
  acl           = "private"
  force_destroy = true
}

resource "yandex_storage_bucket" "bucket_faces" {
  bucket        = var.faces_bucket
  folder_id     = var.folder_id
  acl           = "private"
  force_destroy = true
}

# Создание очереди сообщений
resource "yandex_message_queue" "tasks" {
  name                       = var.queue_name
  visibility_timeout_seconds = 30
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 86400
  access_key                 = yandex_iam_service_account_static_access_key.queue_static_key.access_key
  secret_key                 = yandex_iam_service_account_static_access_key.queue_static_key.secret_key
}

# Создание Yandex Database (serverless)
resource "yandex_ydb_database_serverless" "db" {
  name                = var.db_name
  deletion_protection = false

}

resource "yandex_ydb_table" "ydb_table" {
  path              = "photos"
  connection_string = yandex_ydb_database_serverless.db.ydb_full_endpoint

  column {
    name     = "face_id"
    type     = "String"
    not_null = true
  }
  column {
    name     = "image_id"
    type     = "String"
    not_null = true
  }
  column {
    name     = "face_name"
    type     = "String"
    not_null = false
  }


  primary_key = ["face_id"]
}

# API Gateway
resource "yandex_api_gateway" "apigw" {
  name = var.api_gateway
  spec = <<-EOT
  openapi: 3.0.0
  info:
    title: Face API Gateway
    version: 1.0.0
  paths:
    /:
      get:
        operationId: getFace
        parameters:
          - name: face
            in: query
            required: true
            schema:
              type: string
        responses:
          '200':
            description: Face image
            content:
              'image/jpeg':
                schema:
                  type: "string"
                  format: "binary"
        x-yc-apigateway-integration:
          type: object_storage
          bucket: ${yandex_storage_bucket.bucket_faces.id}
          object: "{face}"
          service_account_id: ${yandex_iam_service_account.saf_bot_account.id}
    /photo:
      get:
        operationId: getPhoto
        parameters:
          - name: photo
            in: query
            required: true
            schema:
              type: string
        responses:
          '200':
            description: Original image
            content:
              'image/jpeg':
                schema:
                  type: "string"
                  format: "binary"
        x-yc-apigateway-integration:
          type: object_storage
          bucket: ${yandex_storage_bucket.bucket_photos.id}
          object: "{photo}"
          service_account_id: ${yandex_iam_service_account.saf_bot_account.id}
EOT
}


# Создание Cloud Functions
resource "yandex_function" "face_detection_func" {
  name              = var.face_detection_function
  user_hash         = archive_file.zip_face_detection.output_sha256
  runtime           = "python312"
  entrypoint        = "index.handler"
  memory            = 128
  execution_timeout = "30"
  content {
    zip_filename = archive_file.zip_face_detection.output_path
  }
  service_account_id = yandex_iam_service_account.saf_bot_account.id
  environment        = {
    "SECRET_KEY" = yandex_message_queue.tasks.secret_key,
    "ACCESS_KEY" = yandex_message_queue.tasks.access_key,
    "QUEUE_URL"  = yandex_message_queue.tasks.id
  }

  mounts {
    name = "bucket_photos"
    mode = "rw"
    object_storage {
      bucket = yandex_storage_bucket.bucket_photos.bucket
    }
  }
}

resource "yandex_function_iam_binding" "face_detection_binding_iam" {
  function_id = yandex_function.face_detection_func.id
  role        = "serverless.functions.invoker"

  members = [
    "serviceAccount:${yandex_iam_service_account.saf_bot_account.id}",
  ]
}

# Trigger face-detection
resource "yandex_function_trigger" "face_detection_trigger" {
  name        = var.face_detection_trigger
  description = "Триггер, вызывающий face-detection"
  folder_id   = var.folder_id
  function {
    id                 = yandex_function.face_detection_func.id
    service_account_id = yandex_iam_service_account.saf_bot_account.id
    retry_attempts     = 2
    retry_interval     = 10
  }
  object_storage {
    bucket_id    = yandex_storage_bucket.bucket_photos.id
    suffix       = ".jpg"
    create       = true
    update       = false
    delete       = false
    batch_cutoff = 1
  }
}


resource "yandex_function" "face_cut_func" {
  name              = var.face_cut_function
  user_hash         = archive_file.zip_face_cut.output_sha256
  runtime           = "python312"
  entrypoint        = "index.handler"
  memory            = 128
  execution_timeout = "30"
  content {
    zip_filename = archive_file.zip_face_cut.output_path
  }
  service_account_id = yandex_iam_service_account.saf_bot_account.id
  mounts {
    name = "bucket_photos"
    mode = "rw"
    object_storage {
      bucket = yandex_storage_bucket.bucket_photos.bucket
    }
  }
  environment = {
    "SECRET_KEY"    = yandex_message_queue.tasks.secret_key,
    "ACCESS_KEY"    = yandex_message_queue.tasks.access_key,
    "BUCKET_FACES"  = yandex_storage_bucket.bucket_faces.id,
    "BUCKET_PHOTOS" = yandex_storage_bucket.bucket_photos.id,
    "YDB_DATABASE"  = yandex_ydb_database_serverless.db.database_path,
    "YDB_ENDPOINT"  = yandex_ydb_database_serverless.db.ydb_api_endpoint
  }
}

resource "yandex_function_iam_binding" "face_cut_binding_iam" {
  function_id = yandex_function.face_cut_func.id
  role        = "serverless.functions.invoker"

  members = [
    "serviceAccount:${yandex_iam_service_account.saf_bot_account.id}",
  ]
}

resource "yandex_function_trigger" "face_cut_trigger" {
  name        = var.face_cut_trigger
  description = "Триггер, вызывающий face-cut"
  folder_id   = var.folder_id
  function {
    id                 = yandex_function.face_cut_func.id
    service_account_id = yandex_iam_service_account.saf_bot_account.id
  }
  message_queue {
    queue_id           = yandex_message_queue.tasks.arn
    service_account_id = yandex_iam_service_account.saf_bot_account.id
    batch_cutoff       = 1
    batch_size         = 1
  }
}

resource "yandex_function" "tg_bot_func" {
  name              = var.bot_function
  user_hash         = archive_file.zip_bot.output_sha256
  runtime           = "python312"
  entrypoint        = "index.handler"
  memory            = 256
  execution_timeout = "30"
  content {
    zip_filename = archive_file.zip_bot.output_path
  }
  service_account_id = yandex_iam_service_account.saf_bot_account.id
  environment        = {
    "SECRET_KEY"         = yandex_message_queue.tasks.secret_key,
    "ACCESS_KEY"         = yandex_message_queue.tasks.access_key,
    "TELEGRAM_BOT_TOKEN" = var.tg_bot_key,
    "API_GATEWAY_URL"    = yandex_api_gateway.apigw.domain,
    "YDB_DATABASE"       = yandex_ydb_database_serverless.db.database_path,
    "YDB_ENDPOINT"       = yandex_ydb_database_serverless.db.ydb_api_endpoint
  }
  mounts {
    name = "bucket_photos"
    mode = "rw"
    object_storage {
      bucket = yandex_storage_bucket.bucket_photos.bucket
    }
  }
  mounts {
    name = "bucket_faces"
    mode = "rw"
    object_storage {
      bucket = yandex_storage_bucket.bucket_faces.bucket
    }
  }
}

resource "yandex_function_iam_binding" "tg_bot_binding_iam" {
  function_id = yandex_function.tg_bot_func.id
  role        = "serverless.functions.invoker"

  members = [
    "system:allUsers",
  ]
}

resource "archive_file" "zip_face_detection" {
  type        = "zip"
  output_path = "face_detection.zip"
  source_dir  = "../src/face-detection"
  excludes    = ["venv", ".env"]
}

resource "archive_file" "zip_face_cut" {
  type        = "zip"
  output_path = "face_cut.zip"
  source_dir  = "../src/face-cut"
  excludes    = ["venv", ".env"]
}

resource "archive_file" "zip_bot" {
  type        = "zip"
  output_path = "tg_bot.zip"
  source_dir  = "../src/bot"
  excludes    = ["venv", ".env"]
}

resource "null_resource" "triggers" {
  triggers = {
    api_key = var.tg_bot_key
  }

  provisioner "local-exec" {
    command = "curl --insecure -X POST https://api.telegram.org/bot${var.tg_bot_key}/setWebhook?url=https://functions.yandexcloud.net/${yandex_function.tg_bot_func.id}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "curl --insecure -X POST https://api.telegram.org/bot${self.triggers.api_key}/deleteWebhook"
  }
}
