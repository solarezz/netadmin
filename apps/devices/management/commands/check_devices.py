from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.devices.models import Device, DeviceStatus
from apps.monitoring.models import Alert
from services.ping_service import ping_multiple
from services import get_connector


class Command(BaseCommand):
    help = 'Проверить доступность всех устройств'

    def _refresh_device_info(self, device):
        """SSH → обновить uptime/model/os после возвращения устройства в online."""
        try:
            connector = get_connector(device)
            with connector:
                info = connector.get_device_info()
            device.uptime     = info.get('uptime', '')
            device.os_version = info.get('os_version', device.os_version)
            device.model      = info.get('model', device.model)
            device.save(update_fields=['uptime', 'os_version', 'model'])
            self.stdout.write(f'  uptime refreshed: {device.name} → {device.uptime}')
        except Exception as e:
            self.stdout.write(f'  uptime refresh failed: {device.name} — {e}')

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
                device.status    = DeviceStatus.ONLINE
                device.last_seen = timezone.now()
                device.save(update_fields=['status', 'last_seen'])
            else:
                device.status = DeviceStatus.OFFLINE
                # Сбрасываем uptime — после перезагрузки старое значение будет некорректным
                device.uptime = ''
                device.save(update_fields=['status', 'last_seen', 'uptime'])

            if old_status == DeviceStatus.ONLINE and device.status == DeviceStatus.OFFLINE:
                Alert.objects.create(
                    device=device,
                    severity=Alert.Severity.CRITICAL,
                    message=f'Устройство {device.name} ({device.ip_address}) недоступно',
                )
                self.stdout.write(self.style.ERROR(f'ALERT: {device.name} is DOWN'))

            elif old_status != DeviceStatus.ONLINE and device.status == DeviceStatus.ONLINE:
                # Устройство вернулось в online — сразу обновляем uptime/info через SSH
                device.alerts.filter(is_resolved=False).update(
                    is_resolved=True, resolved_at=timezone.now()
                )
                self.stdout.write(self.style.SUCCESS(f'RESOLVED: {device.name} is UP'))
                self._refresh_device_info(device)

        online = Device.objects.filter(status=DeviceStatus.ONLINE).count()
        total  = devices.count()
        self.stdout.write(f'Проверка завершена: {online}/{total} устройств online')
