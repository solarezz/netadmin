from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from apps.devices.models import Device, DeviceStatus
from apps.monitoring.models import Alert
from services.ping_service import ping_multiple


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'monitoring/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        devices = Device.objects.all()

        ctx['total_devices'] = devices.count()
        ctx['online_count'] = devices.filter(status=DeviceStatus.ONLINE).count()
        ctx['offline_count'] = devices.filter(status=DeviceStatus.OFFLINE).count()
        ctx['warning_count'] = devices.filter(status=DeviceStatus.WARNING).count()
        ctx['devices'] = devices
        ctx['recent_alerts'] = Alert.objects.filter(is_resolved=False)[:10]

        return ctx


class CheckAllDevicesView(LoginRequiredMixin, View):
    def post(self, request):
        devices = Device.objects.all()
        ip_list = [str(d.ip_address) for d in devices]

        results = ping_multiple(ip_list)
        result_map = {r['ip']: r for r in results}

        updated = 0
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
            elif old_status == DeviceStatus.OFFLINE and device.status == DeviceStatus.ONLINE:
                device.alerts.filter(is_resolved=False).update(
                    is_resolved=True, resolved_at=timezone.now()
                )
            updated += 1

        online = Device.objects.filter(status=DeviceStatus.ONLINE).count()
        return JsonResponse({
            'success': True,
            'message': f'Проверено {updated} устройств. Online: {online}/{devices.count()}',
            'online': online,
            'total': devices.count(),
        })


class ResolveAlertView(LoginRequiredMixin, View):
    """
    POST /alerts/<id>/resolve/
    Закрывает алерт (нажатие "✓ Закрыть" на Dashboard).
    """
    def post(self, request, alert_id):
        try:
            alert = Alert.objects.get(pk=alert_id, is_resolved=False)
            alert.is_resolved = True
            alert.resolved_at = timezone.now()
            alert.save(update_fields=['is_resolved', 'resolved_at'])
            remaining = Alert.objects.filter(is_resolved=False).count()
            return JsonResponse({'success': True, 'remaining': remaining})
        except Alert.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Алерт не найден'}, status=404)


class DeviceStatusApiView(LoginRequiredMixin, View):
    """
    GET /api/devices/status/
    JSON-список статусов всех устройств для AJAX auto-refresh.
    """
    def get(self, request):
        devices = Device.objects.values(
            'id', 'name', 'status', 'last_seen', 'uptime'
        )
        data = []
        for d in devices:
            data.append({
                'id': d['id'],
                'name': d['name'],
                'status': d['status'],
                'last_seen': d['last_seen'].strftime('%d.%m.%Y %H:%M') if d['last_seen'] else '—',
                'uptime': d['uptime'] or '—',
            })
        active_alerts = Alert.objects.filter(is_resolved=False).count()
        return JsonResponse({'devices': data, 'active_alerts': active_alerts})
