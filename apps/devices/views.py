from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.accounts.mixins import OperatorRequiredMixin
from django.contrib import messages
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

    def get_queryset(self):
        qs = super().get_queryset()
        device_type = self.request.GET.get('type')
        status = self.request.GET.get('status')
        if device_type:
            qs = qs.filter(device_type=device_type)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['device_types'] = DeviceType.choices
        ctx['statuses'] = DeviceStatus.choices
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
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


def _build_connection_message(ping_ok, tcp_ok, port):
    if not ping_ok:
        return f'Устройство не отвечает на ping'
    if not tcp_ok:
        return f'Ping OK, но порт {port} недоступен (SSH закрыт или неверный порт)'
    return f'Связь установлена: ping OK, порт {port} открыт'
