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
    JSON-список статусов всех устройств + активные алерты для AJAX auto-refresh.
    """
    def get(self, request):
        devices = Device.objects.values('id', 'name', 'status', 'last_seen', 'uptime')
        data = []
        for d in devices:
            data.append({
                'id': d['id'],
                'name': d['name'],
                'status': d['status'],
                'last_seen': d['last_seen'].strftime('%d.%m.%Y %H:%M') if d['last_seen'] else '—',
                'uptime': d['uptime'] or '—',
            })

        # Последние 10 активных алертов для обновления блока на дашборде
        alerts_qs = Alert.objects.filter(is_resolved=False).select_related('device')[:10]
        alerts = []
        for a in alerts_qs:
            alerts.append({
                'id': a.pk,
                'device_name': a.device.name,
                'severity': a.severity,
                'message': a.message,
                'created_at': a.created_at.strftime('%d.%m %H:%M'),
            })

        return JsonResponse({
            'devices': data,
            'active_alerts': len(alerts),
            'alerts': alerts,
        })


class TopologyView(LoginRequiredMixin, TemplateView):
    template_name = 'monitoring/topology.html'


class TopologyApiView(LoginRequiredMixin, View):
    """GET /api/topology/ — узлы и рёбра для vis.js Network.
    Рёбра строятся автоматически через LLDP (/ip neighbor print) на каждом MikroTik.
    Результат кешируется на 60 секунд чтобы не нагружать SSH при авто-обновлении.
    """

    STATUS_COLORS = {
        'online':  {'background': '#10b981', 'border': '#047857', 'font': '#ffffff'},
        'offline': {'background': '#ef4444', 'border': '#b91c1c', 'font': '#ffffff'},
        'warning': {'background': '#f59e0b', 'border': '#b45309', 'font': '#ffffff'},
        'unknown': {'background': '#64748b', 'border': '#334155', 'font': '#ffffff'},
    }
    SHAPES = {
        'mikrotik_router': 'diamond',
        'mikrotik_switch': 'hexagon',
        'linux':           'ellipse',
    }

    _cache = {'data': None, 'ts': 0}
    CACHE_TTL = 120

    def get(self, request):
        import time
        now = time.time()
        if self._cache['data'] and (now - self._cache['ts']) < self.CACHE_TTL:
            return JsonResponse(self._cache['data'])

        devices = list(Device.objects.all())
        ip_to_device = {str(d.ip_address): d for d in devices}

        nodes = [self._make_node(d) for d in devices]
        edges = self._discover_edges(devices, ip_to_device)

        data = {'nodes': nodes, 'edges': edges}
        self._cache['data'] = data
        self._cache['ts'] = now
        return JsonResponse(data)

    def _make_node(self, d):
        is_core = 'core' in d.name.lower() or 'perimeter' in d.name.lower()
        try:
            from apps.monitoring.models import DeviceMetric
            metric = DeviceMetric.objects.filter(device=d).first()
            cpu = metric.cpu_usage if metric else None
            ram = metric.memory_usage if metric else None
        except Exception:
            cpu = None
            ram = None
        return {
            'id':          d.pk,
            'label':       d.name,
            'ip':          str(d.ip_address),
            'is_core':     is_core,
            'device_type': d.device_type,
            'model':       d.model or '',
            'uptime':      d.uptime or '',
            'cpu':         cpu,
            'ram':         ram,
            'title': f'{d.ip_address} | {d.get_status_display()}',
            'shape': self.SHAPES.get(d.device_type, 'ellipse'),
            'color': self.STATUS_COLORS.get(d.status, self.STATUS_COLORS['unknown']),
            'url':   f'/devices/{d.pk}/',
            'status': d.status,
        }


    def _discover_edges(self, devices, ip_to_device):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from services.mikrotik_manager import MikroTikManager

        online_mikrotik = [
            d for d in devices
            if 'mikrotik' in d.device_type and d.status == 'online'
        ]
        linux_ips = {str(d.ip_address): d for d in devices if d.device_type == 'linux'}

        def fetch(device):
            try:
                with MikroTikManager(device) as mgr:
                    mndp = mgr.get_neighbors_structured()
                    arp  = mgr.get_arp_table_structured() if linux_ips else []
                    try:
                        ospf = mgr.get_ospf_neighbors()
                    except Exception:
                        ospf = []
                    return device, mndp, arp, ospf
            except Exception:
                return device, [], [], []

        all_results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch, d): d for d in online_mikrotik}
            for future in as_completed(futures, timeout=20):
                try:
                    all_results.append(future.result())
                except Exception:
                    pass

        # Sort by device name — guarantees deterministic processing order
        all_results.sort(key=lambda r: r[0].name)

        edge_set = set()
        ospf_connected = set()  # pks of devices that have at least one confirmed OSPF link

        # Phase 1 — OSPF: only directly-adjacent routing neighbors.
        # OSPF adjacencies are link-scoped; unlike MNDP they never span multiple hops.
        for device, _, _, ospf_nbrs in all_results:
            for nbr in ospf_nbrs:
                # Try neighbor address first, then OSPF router-id (often = management IP)
                neighbor = (ip_to_device.get(nbr['address']) or
                            ip_to_device.get(nbr['router_id']))
                if not neighbor or 'mikrotik' not in neighbor.device_type:
                    continue
                edge_set.add(tuple(sorted([device.pk, neighbor.pk])))
                ospf_connected.add(device.pk)
                ospf_connected.add(neighbor.pk)

        # Phase 2 — ARP for non-OSPF MikroTik devices (L2 switches, test routers).
        # Among all routers that see the device in ARP, pick the alphabetically-first
        # one that reports it on a non-mgmt interface (deterministic).
        switch_candidates = {}  # switch_pk -> [(router_pk, is_non_mgmt)]
        for device, _, arp_entries, _ in all_results:
            for entry in arp_entries:
                seen = ip_to_device.get(entry['ip'])
                if not seen or seen.pk == device.pk:
                    continue
                if 'mikrotik' not in seen.device_type:
                    continue
                if seen.pk in ospf_connected:
                    continue  # already wired via OSPF
                is_non_mgmt = entry.get('interface', '') not in ('ether1', 'bridge', 'bridge1')
                switch_candidates.setdefault(seen.pk, []).append((device.pk, is_non_mgmt))

        for switch_pk, candidates in switch_candidates.items():
            # prefer non-mgmt interface; break ties alphabetically by router_pk
            candidates.sort(key=lambda c: (not c[1], c[0]))
            edge_set.add(tuple(sorted([switch_pk, candidates[0][0]])))

        # Phase 3 — ARP for Linux servers (deterministic: sorted device order, non-mgmt wins).
        linux_connections = {}
        for device, _, arp_entries, _ in all_results:
            for entry in arp_entries:
                linux = linux_ips.get(entry['ip'])
                if not linux:
                    continue
                is_non_mgmt = entry.get('interface', '') not in ('ether1', 'bridge', 'bridge1')
                existing = linux_connections.get(linux.pk)
                if not existing or (is_non_mgmt and not existing[1]):
                    linux_connections[linux.pk] = (device.pk, is_non_mgmt)

        for linux_pk, (mikrotik_pk, _) in linux_connections.items():
            edge_set.add(tuple(sorted([linux_pk, mikrotik_pk])))

        return [{'id': i + 1, 'from': a, 'to': b} for i, (a, b) in enumerate(sorted(edge_set))]



class DeviceMetricsApiView(LoginRequiredMixin, View):
    """
    GET /api/devices/<pk>/metrics/
    Возвращает последнюю метрику из БД (без SSH, дёшево).
    Используется для auto-refresh на странице устройства.
    """
    def get(self, request, pk):
        from apps.monitoring.models import DeviceMetric
        try:
            device = Device.objects.get(pk=pk)
        except Device.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

        metric = DeviceMetric.objects.filter(device=device).first()
        if metric:
            return JsonResponse({
                'cpu':       metric.cpu_usage,
                'ram':       metric.memory_usage,
                'timestamp': metric.timestamp.strftime('%d.%m.%Y %H:%M:%S'),
                'uptime':    device.uptime or '—',
                'os':        device.os_version or '—',
                'model':     device.model or '—',
            })
        return JsonResponse({'cpu': None, 'ram': None, 'timestamp': None,
                             'uptime': device.uptime or '—',
                             'os': device.os_version or '—',
                             'model': device.model or '—'})
