from django.core.management.base import BaseCommand
from apps.devices.models import Device


class Command(BaseCommand):
    help = 'Заполнить БД тестовыми устройствами'

    def handle(self, *args, **options):
        devices_data = [
            {
                'name': 'MIK-R1',
                'device_type': 'mikrotik_router',
                'ip_address': '10.1.1.1',
                'username': 'netadmin',
                'password': 'NetAdmin2026!',
                'location': 'Серверная, шкаф 1',
                'description': 'Основной маршрутизатор. OSPF, NAT, DHCP, Firewall.',
            },
            {
                'name': 'MIK-R2',
                'device_type': 'mikrotik_router',
                'ip_address': '10.1.1.2',
                'username': 'netadmin',
                'password': 'NetAdmin2026!',
                'location': 'Серверная, шкаф 1',
                'description': 'Резервный маршрутизатор. OSPF, DHCP для 2 этажа.',
            },
            {
                'name': 'MIK-SW1',
                'device_type': 'mikrotik_switch',
                'ip_address': '10.1.1.11',
                'username': 'netadmin',
                'password': 'NetAdmin2026!',
                'location': '1 этаж, коммутационный шкаф',
                'description': 'Коммутатор 1 этажа. Bridge-режим.',
            },
            {
                'name': 'MIK-SW2',
                'device_type': 'mikrotik_switch',
                'ip_address': '10.1.1.12',
                'username': 'netadmin',
                'password': 'NetAdmin2026!',
                'location': '2 этаж, коммутационный шкаф',
                'description': 'Коммутатор 2 этажа. Bridge-режим.',
            },
            {
                'name': 'SRV1-FILE',
                'device_type': 'linux',
                'ip_address': '10.1.1.101',
                'username': 'netadmin',
                'password': '123123123',
                'location': 'Серверная, шкаф 2',
                'description': 'Файловый сервер. Ubuntu 22.04. Samba.',
            },
            {
                'name': 'SRV2-WEB',
                'device_type': 'linux',
                'ip_address': '10.1.1.102',
                'username': 'srv2-web',
                'password': '123123123',
                'location': 'Серверная, шкаф 2',
                'description': 'Веб-сервер. Ubuntu 22.04. Nginx.',
            },
        ]

        created = 0
        for data in devices_data:
            device, is_new = Device.objects.get_or_create(
                ip_address=data['ip_address'],
                defaults=data,
            )
            if is_new:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'Создано: {device.name}'))
            else:
                self.stdout.write(f'Уже существует: {device.name}')

        self.stdout.write(f'\nГотово: создано {created}, уже было {len(devices_data) - created}')
