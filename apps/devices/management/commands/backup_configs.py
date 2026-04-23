import hashlib
from django.core.management.base import BaseCommand
from apps.devices.models import Device, DeviceStatus
from apps.backups.models import ConfigBackup
from services import get_connector


class Command(BaseCommand):
    help = 'Бэкап конфигураций всех online-устройств'

    def handle(self, *args, **options):
        devices = Device.objects.filter(status=DeviceStatus.ONLINE)
        success, skip, error = 0, 0, 0

        for device in devices:
            try:
                connector = get_connector(device)
                with connector:
                    config = connector.get_running_config()

                new_hash = hashlib.sha256(config.encode()).hexdigest()
                last_backup = device.backups.first()

                if last_backup and last_backup.config_hash == new_hash:
                    skip += 1
                    self.stdout.write(f'SKIP: {device.name} — без изменений')
                else:
                    ConfigBackup.objects.create(
                        device=device, config_text=config, is_automatic=True,
                    )
                    success += 1
                    self.stdout.write(self.style.SUCCESS(f'OK: {device.name}'))
            except Exception as e:
                error += 1
                self.stdout.write(self.style.ERROR(f'ERROR: {device.name} — {e}'))

        self.stdout.write(f'\nГотово: {success} сохранено, {skip} без изменений, {error} ошибок')
