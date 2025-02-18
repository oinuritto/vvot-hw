variable "sa_account" {
  description = "ID сервизного аккаунта"
  type        = string
  default     = "saf-bot-account"
}

variable "cloud_id" {
  description = "ID облака в Yandex Cloud"
  type        = string
}

variable "folder_id" {
  description = "ID папки в Yandex Cloud"
  type        = string
}

variable "region_name" {
  type        = string
  description = "Регион"
  default     = "ru-central1"
}

variable "photos_bucket" {
  description = "Название бакета для оригинальных фотографий"
  type        = string
  default     = "vvot08-photos"
}

variable "faces_bucket" {
  description = "Название бакета для фотографий лиц"
  type        = string
  default     = "vvot08-faces"
}

variable "queue_name" {
  description = "Название очереди сообщений"
  type        = string
  default     = "vvot08-tasks"
}

variable "bot_function" {
  description = "Название функции для Telegram бота"
  type        = string
  default     = "vvot08-boot"
}

variable "face_detection_function" {
  description = "Название функции для face-detection"
  type        = string
  default     = "vvot08-face-detection"
}

variable "face_cut_function" {
  description = "Название функции для face-cut"
  type        = string
  default     = "vvot08-face-cut"
}

variable "face_detection_trigger" {
  description = "Название триггера для face-detection"
  type        = string
  default     = "vvot08-photo"
}

variable "face_cut_trigger" {
  description = "Название триггера для face-cut"
  type        = string
  default     = "vvot08-task"
}

variable "tg_bot_key" {
  description = "Telegram Bot Token"
  type        = string
  sensitive   = true
}

variable "api_gateway" {
  description = "Название API Gateway"
  type        = string
  default     = "vvot08-apigw"
}

variable "db_name" {
  description = "Название базы данных для фотографий"
  type        = string
  default     = "vvot08-db-photo-face"
}

variable "key_file_path" {
  type        = string
  description = "Ключ сервисного аккаунта"
  default     = "C:\\Users\\oinuritto\\.yc-keys\\key.json"
}