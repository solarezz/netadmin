from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.accounts.mixins import OperatorRequiredMixin
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
import socket
from .models import Device, CommandLog, DeviceType, DeviceStatus
from services import get_connector
from services.ping_service import ping_host


class DeviceListView(LoginRequiredMixin, ListView):
    model = Device
    template_name = 'devices/device_list.html'
    context_object_name = 'devices'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
        device_type = self.request.GET.get('type', '').strip()
        status      = self.request.GET.get('status', '').strip()
        q           = self.request.GET.get('q', '').strip()
        if device_type:
            qs = qs.filter(device_type=device_type)
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(ip_address__icontains=q) |
                Q(model__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Global counts (unfiltered) for tab badges
        agg = Device.objects.aggregate(
            total=Count('pk'),
            online=Count('pk',  filter=Q(status=DeviceStatus.ONLINE)),
            offline=Count('pk', filter=Q(status=DeviceStatus.OFFLINE)),
            warning=Count('pk', filter=Q(status=DeviceStatus.WARNING)),
        )
        ctx['count_total']   = agg['total']
        ctx['count_online']  = agg['online']
        ctx['count_offline'] = agg['offline']
        ctx['count_warning'] = agg['warning']

        # Active alerts count
        from apps.monitoring.models import Alert
        ctx['count_alerts'] = Alert.objects.filter(is_resolved=False).count()

        # Filter state for re-rendering
        ctx['device_types']    = DeviceType.choices
        ctx['statuses']        = DeviceStatus.choices
        ctx['selected_type']   = self.request.GET.get('type', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_q']      = self.request.GET.get('q', '')

        # Latest metric per device (current page only — one query)
        from apps.monitoring.models import DeviceMetric
        device_pks = [d.pk for d in ctx['devices']]
        latest_metrics = {}
        for m in DeviceMetric.objects.filter(device_id__in=device_pks).order_by('-timestamp'):
            if m.device_id not in latest_metrics:
                latest_metrics[m.device_id] = m
        ctx['latest_metrics'] = latest_metrics

        return ctx


class DeviceDetailView(LoginRequiredMixin, DetailView):
    model = Device
    template_name = 'devices/device_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        device = self.get_object()
        ctx['recent_commands'] = device.command_logs.all()[:20]
        ctx['recent_backups'] = device.backups.all()[:5]
        ctx['recent_metrics'] = device.metrics.all()[:50]
        return ctx


class DeviceCreateView(OperatorRequiredMixin, LoginRequiredMixin, CreateView):
    model = Device
    template_name = 'devices/device_form.html'
    fields = ['name', 'device_type', 'ip_address', 'ssh_port',
              'username', 'password', 'location', 'description']
    success_url = reverse_lazy('device-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Добавить устройство'
        return ctx

    def form_valid(self, form):
        device = form.save(commit=False)
        result = ping_host(device.ip_address, count=2, timeout=2)
        device.status = DeviceStatus.ONLINE if result['alive'] else DeviceStatus.OFFLINE
        device.save()
        messages.success(
            self.request,
            f'Устройство «{device.name}» добавлено. '
            f'Статус: {"Online ✓" if result["alive"] else "Offline (не отвечает на ping)"}'
        )
        return redirect(self.success_url)


class DeviceUpdateView(OperatorRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Device
    template_name = 'devices/device_form.html'
    fields = ['name', 'device_type', 'ip_address', 'ssh_port',
              'username', 'password', 'location', 'description']
    success_url = reverse_lazy('device-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Редактировать устройство'
        return ctx


class DeviceDeleteView(OperatorRequiredMixin, LoginRequiredMixin, DeleteView):
    model = Device
    template_name = 'devices/device_confirm_delete.html'
    success_url = reverse_lazy('device-list')


class DeviceExecuteView(OperatorRequiredMixin, LoginRequiredMixin, View):
    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)
        suggested_commands = self._get_suggested_commands(device.device_type)
        return render(request, 'devices/device_execute.html', {
            'device': device,
            'suggested_commands': suggested_commands,
            'recent_commands': device.command_logs.all()[:10],
        })

    def post(self, request, pk):
        device = get_object_or_404(Device, pk=pk)
        command = request.POST.get('command', '').strip()

        if not command:
            return JsonResponse({'error': 'Команда не может быть пустой'}, status=400)

        try:
            connector = get_connector(device)
            with connector:
                output = connector.execute_command(command)

            CommandLog.objects.create(
                device=device, command=command, output=output,
                user=request.user, success=True,
            )
            return JsonResponse({'output': output, 'success': True})

        except Exception as e:
            CommandLog.objects.create(
                device=device, command=command, output=str(e),
                user=request.user, success=False,
            )
            return JsonResponse({'output': str(e), 'success': False}, status=500)

    def _get_suggested_commands(self, device_type):  # noqa: keep method grouping
        commands = {
            'mikrotik_router': [
                '/system identity print',
                '/system resource print',
                '/interface print',
                '/ip address print',
                '/ip route print',
                '/routing ospf neighbor print',
                '/ip firewall filter print',
                '/ip firewall nat print',
                '/ip dhcp-server lease print',
                '/ip arp print',
                '/export',
            ],
            'mikrotik_switch': [
                '/system identity print',
                '/system resource print',
                '/interface print',
                '/interface bridge print',
                '/interface bridge port print',
                '/ip address print',
                '/ip arp print',
                '/export',
            ],
            'linux': [
                'uname -a',
                'uptime',
                'hostname',
                'df -h',
                'free -h',
                'ip addr show',
                'ip route show',
                'ss -tlnp',
                'systemctl list-units --type=service --state=running --no-pager | head -20',
                'cat /etc/os-release',
            ],
        }
        return commands.get(device_type, [])


class TestConnectionView(LoginRequiredMixin, View):
    """AJAX: проверяет ping + TCP-порт до добавления устройства."""

    def post(self, request):
        import json
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Неверный формат запроса'}, status=400)

        ip = data.get('ip', '').strip()
        port = int(data.get('port', 22))
        username = data.get('username', '').strip()

        if not ip:
            return JsonResponse({'error': 'IP-адрес обязателен'}, status=400)

        ping_result = ping_host(ip, count=2, timeout=2)

        tcp_ok = False
        if ping_result['alive']:
            try:
                with socket.create_connection((ip, port), timeout=3):
                    tcp_ok = True
            except OSError:
                tcp_ok = False

        return JsonResponse({
            'ping': ping_result['alive'],
            'rtt_ms': ping_result['rtt_ms'],
            'tcp_port': port,
            'tcp_ok': tcp_ok,
            'message': _build_connection_message(ping_result['alive'], tcp_ok, port),
        })


class ConnectedDevicesView(LoginRequiredMixin, View):
    """AJAX: возвращает список устройств из DHCP-аренды и ARP-таблицы MikroTik."""

    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)

        if 'mikrotik' not in device.device_type:
            return JsonResponse({'error': 'Только для MikroTik'}, status=400)

        if device.status == DeviceStatus.OFFLINE:
            return JsonResponse({'error': 'Устройство недоступно (offline)'}, status=503)

        try:
            from services.mikrotik_manager import MikroTikManager
            manager = MikroTikManager(device)
            with manager:
                dhcp = manager.get_dhcp_leases_structured()
                arp = manager.get_arp_table_structured()

            # Объединяем: DHCP-записи приоритетнее, ARP дополняет
            seen_ips = {d['ip'] for d in dhcp}
            combined = dhcp + [a for a in arp if a['ip'] not in seen_ips]
            combined.sort(key=lambda x: x['ip'])

            return JsonResponse({'devices': combined, 'count': len(combined)})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class DeviceServiceDateView(OperatorRequiredMixin, LoginRequiredMixin, View):
    """AJAX: сохранить / сбросить дату обслуживания устройства."""

    def post(self, request, pk):
        import json
        device = get_object_or_404(Device, pk=pk)
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Неверный формат'}, status=400)

        raw = data.get('date', '').strip()
        if raw:
            from datetime import date
            try:
                year, month, day = raw.split('-')
                device.serviced_at = date(int(year), int(month), int(day))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Неверный формат даты (YYYY-MM-DD)'}, status=400)
        else:
            device.serviced_at = None

        device.save(update_fields=['serviced_at'])
        return JsonResponse({
            'ok': True,
            'date': device.serviced_at.strftime('%d.%m.%Y') if device.serviced_at else None,
        })


def _build_connection_message(ping_ok, tcp_ok, port):
    if not ping_ok:
        return f'Устройство не отвечает на ping'
    if not tcp_ok:
        return f'Ping OK, но порт {port} недоступен (SSH закрыт или неверный порт)'
    return f'Связь установлена: ping OK, порт {port} открыт'
