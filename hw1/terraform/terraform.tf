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
  service_account_key_file = "C:\\Users\\oinuritto\\.yc-keys\\key.json"
}

resource "yandex_storage_bucket" "tg_bot_bucket" {
  bucket    = var.bucket_name
  folder_id = var.folder_id
}

resource "yandex_storage_object" "yagpt_setup" {
  bucket = yandex_storage_bucket.tg_bot_bucket.id
  key    = "instruction.txt"
  source = "instruction.txt"
}

resource "yandex_function" "handler_func" {
  name               = "func-bot"
  user_hash          = archive_file.zip.output_sha256
  runtime            = "python312"
  entrypoint         = "bot.handler"
  memory             = 128
  execution_timeout  = 20
  service_account_id = "aje6p76sbv6lm7hqqq8e"

  environment = {
    TG_BOT_KEY            = var.tg_bot_key,
    YC_BUCKET_NAME        = var.bucket_name
    YC_FOLDER_ID          = var.folder_id
    AWS_ACCESS_KEY_ID     = var.aws_access_key_id,
    AWS_SECRET_ACCESS_KEY = var.aws_secret_access_key,
    AWS_DEFAULT_REGION    = var.region_name,
    YANDEX_API_KEY        = var.yandex_api_key
  }

  mounts {
    name = var.bucket_name
    mode = "ro"
    object_storage {
      bucket = yandex_storage_bucket.tg_bot_bucket.bucket
    }
  }

  content {
    zip_filename = archive_file.zip.output_path
  }
}

output "func_url" {
  value = "https://functions.yandexcloud.net/${yandex_function.handler_func.id}"
}

resource "archive_file" "zip" {
  type        = "zip"
  output_path = "src.zip"
  source_dir  = "../bot"
  excludes    = ["venv", ".env"]
}


resource "yandex_function_iam_binding" "function-iam" {
  function_id = yandex_function.handler_func.id
  role        = "serverless.functions.invoker"

  members = [
    "system:allUsers",
  ]
}

resource "null_resource" "triggers" {
  triggers = {
    api_key = var.tg_bot_key
  }

  provisioner "local-exec" {
    command = "curl --insecure -X POST https://api.telegram.org/bot${var.tg_bot_key}/setWebhook?url=https://functions.yandexcloud.net/${yandex_function.handler_func.id}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "curl --insecure -X POST https://api.telegram.org/bot${self.triggers.api_key}/deleteWebhook"
  }
}

# Переменные
variable "tg_bot_key" {
  type        = string
  description = "Ключ Telegram-бота"
}

variable "cloud_id" {
  type        = string
  description = "ID облака"
}

variable "folder_id" {
  type        = string
  description = "ID каталога"
}

variable "bucket_name" {
  type        = string
  description = "Название бакета, в котором находится объект с инструкцией к YandexGPT"
  default     = "tg-bot-bucket-vvot08"
}

variable "aws_access_key_id" {
  description = "Идентификатор ключа AWS"
  type        = string
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "Секретный ключ AWS"
  type        = string
  sensitive   = true
}

variable "region_name" {
  type        = string
  description = "Регион"
  default     = "ru-central1"
}

variable "yandex_api_key" {
  description = "API KEY для Yandex сервисов"
  type        = string
  sensitive   = true
}
