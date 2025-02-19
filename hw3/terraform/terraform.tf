terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
    }
  }
  required_version = ">= 0.13"
}

provider "yandex" {
  service_account_key_file = pathexpand(var.key_file_path)
  cloud_id  = var.cloud_id
  folder_id = var.folder_id
  zone      = var.region_name
}

resource "yandex_vpc_network" "network" {
  name = "vvot08-nextcloud-network"
}

resource "yandex_vpc_subnet" "subnet" {
  name       = "vvot08-nextcloud-subnet"
  zone       = var.region_name
  v4_cidr_blocks = ["192.168.10.0/24"]
  network_id = yandex_vpc_network.network.id
}

data "yandex_compute_image" "ubuntu" {
  family = "ubuntu-2404-lts-oslogin"
}

resource "yandex_compute_disk" "boot-disk" {
  name     = "vvot08-nextcloud-boot-disk"
  type     = "network-ssd"
  image_id = data.yandex_compute_image.ubuntu.id
  size     = 20
}

resource "yandex_compute_instance" "server" {
  name        = "vvot08-nextcloud-server"
  platform_id = "standard-v3"
  hostname    = "nextcloud"

  resources {
    core_fraction = 20
    cores         = 2
    memory        = 4
  }

  boot_disk {
    disk_id = yandex_compute_disk.boot-disk.id
  }

  network_interface {
    subnet_id = yandex_vpc_subnet.subnet.id
    nat       = true
  }

  metadata = {
    ssh-keys = "${var.vm_username}:${file("~/.ssh/id_rsa.pub")}"
  }
}

output "nextcloud-ip" {
  value = yandex_compute_instance.server.network_interface[0].nat_ip_address
}