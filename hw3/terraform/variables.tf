variable "region_name" {
  type        = string
  description = "Region"
  default     = "ru-central1-a"
}

variable "cloud_id" {
  type = string
  description = "Cloud ID"
}

variable "folder_id" {
  type        = string
  description = "Folder ID"
}

variable "vm_username" {
  type = string
}

variable "key_file_path" {
  type        = string
  description = "Key file path"
  default     = "C:\\Users\\oinuritto\\.yc-keys\\key.json"
}