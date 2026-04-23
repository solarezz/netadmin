from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.devices.models import Device, DeviceStatus
from apps.monitoring.models import Alert
from services.ping_service import ping_multiple


class Command(BaseCommand):
    help = 'Проверить доступность всех устройств'

    def handle(self, *args, **options):
        devices = Device.objects.all()
        ip_list = [str(d.ip_address) for d in devices]

        results = ping_multiple(ip_list)
        result_map = {r['ip']: r for r in results}

        for device in devices:
            ping_result = result_map.get(str(device.ip_address))
            if not ping_result:
                continue

            old_status = device.status

            if ping_result['alive']:
                device.status = DeviceStatus.ONLINE
                device.last_seen = timezone.now()
            else:
                device.status = DeviceStatus.OFFLINE

            device.save(update_fields=['status', 'last_seen'])

            if old_status == DeviceStatus.ONLINE and device.status == DeviceStatus.OFFLINE:
                Alert.objects.create(
                    device=device,
                    severity=Alert.Severity.CRITICAL,
                    message=f'Устройство {device.name} ({device.ip_address}) недоступно',
                )
                self.stdout.write(self.style.ERROR(f'ALERT: {device.name} is DOWN'))
            elif old_status == DeviceStatus.OFFLINE and device.status == DeviceStatus.ONLINE:
                device.alerts.filter(is_resolved=False).update(
                    is_resolved=True, resolved_at=timezone.now()
                )
                self.stdout.write(self.style.SUCCESS(f'RESOLVED: {device.name} is UP'))

        online = Device.objects.filter(status=DeviceStatus.ONLINE).count()
        total = devices.count()
        self.stdout.write(f'Проверка завершена: {online}/{total} устройств online')
