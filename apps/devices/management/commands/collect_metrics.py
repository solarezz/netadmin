from django.core.management.base import BaseCommand
from apps.devices.models import Device, DeviceStatus
from apps.monitoring.models import DeviceMetric
from services import get_connector


class Command(BaseCommand):
    help = 'Собрать метрики с online-устройств'

    def handle(self, *args, **options):
        devices = Device.objects.filter(status=DeviceStatus.ONLINE)

        for device in devices:
            try:
                connector = get_connector(device)
                with connector:
                    info = connector.get_device_info()
                    device.os_version = info.get('os_version', '')
                    device.uptime = info.get('uptime', '')
                    device.model = info.get('model', '')
                    device.save(update_fields=['os_version', 'uptime', 'model'])

                    cpu = connector.get_cpu_usage()
                    memory = connector.get_memory_usage()

                    DeviceMetric.objects.create(
                        device=device,
                        cpu_usage=cpu,
                        memory_usage=memory,
                        extra_data={'interfaces': connector.get_interfaces()},
                    )

                self.stdout.write(self.style.SUCCESS(f'OK: {device.name}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'ERROR: {device.name} — {e}'))
