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
    CACHE_TTL = 30

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
        from services.mikrotik_manager import MikroTikManager
        from services.linux_manager import LinuxManager
        from concurrent.futures import ThreadPoolExecutor

        pk_to_device   = {d.pk: d for d in devices}
        name_to_device = {d.name: d for d in devices}   # for MNDP identity matching
        mikrotik_devs  = sorted([d for d in devices if 'mikrotik' in d.device_type], key=lambda x: x.name)
        linux_devs     = sorted([d for d in devices if d.device_type == 'linux'],    key=lambda x: x.name)

        def fetch_mikrotik(device):
            try:
                mgr = MikroTikManager(device)
                mgr.connect()
                try:
                    mndp   = mgr.get_neighbors_structured()
                    arp    = mgr.get_arp_table_structured()
                    gw     = mgr.get_default_gateway()
                    mt_ips = mgr.get_all_ips()
                finally:
                    mgr.disconnect()
            except Exception:
                mndp, arp, gw, mt_ips = [], [], '', []
            return device.pk, mndp, arp, gw, mt_ips

        def fetch_linux(device):
            try:
                mgr = LinuxManager(device)
                mgr.connect()
                try:
                    ips = mgr.get_all_ips()
                    gw  = mgr.get_default_gateway()
                finally:
                    mgr.disconnect()
            except Exception:
                ips, gw = [], ''
            return device.pk, ips, gw

        with ThreadPoolExecutor(max_workers=8) as executor:
            mt_futures = [executor.submit(fetch_mikrotik, d) for d in mikrotik_devs]
            lx_futures = [executor.submit(fetch_linux, d)    for d in linux_devs]
            mt_results = sorted([f.result() for f in mt_futures], key=lambda x: x[0])
            lx_results = sorted([f.result() for f in lx_futures], key=lambda x: x[0])

        # Extended IP map: mgmt IPs + MikroTik LAN IPs + Linux secondary IPs.
        # Needed because MNDP/ARP/gateway use LAN IPs (10.1.10.x, 10.1.20.x) not in the DB.
        extended_ip_map = dict(ip_to_device)
        for pk, _m, _a, _g, mt_ips in mt_results:
            dev = pk_to_device.get(pk)
            if dev:
                for ip in mt_ips:
                    if ip not in extended_ip_map:
                        extended_ip_map[ip] = dev
        for pk, ips, _gw in lx_results:
            dev = pk_to_device.get(pk)
            if dev:
                for ip in ips:
                    if ip not in extended_ip_map:
                        extended_ip_map[ip] = dev

        edge_set      = set()
        lan_connected = set()

        # Phase 1: MikroTik↔MikroTik via MNDP — skip ether1 (management).
        # Primary lookup by neighbor IP; fallback by MNDP identity (device name)
        # because routers advertise their LAN IP which may differ from DB mgmt IP.
        for pk, mndp, _a, _g, _i in mt_results:
            for nbr in mndp:
                iface = nbr.get('interface', '')
                if not iface or iface == 'ether1':
                    continue
                nbr_dev = (ip_to_device.get(nbr.get('address', ''))
                           or name_to_device.get(nbr.get('identity', '')))
                if nbr_dev and nbr_dev.pk != pk and 'mikrotik' in nbr_dev.device_type:
                    edge = tuple(sorted([pk, nbr_dev.pk]))
                    edge_set.add(edge)
                    lan_connected.update([pk, nbr_dev.pk])

        # Phase 2a: Switch ARP → Linux (switches are the preferred L2 connection point)
        for pk, _m, arp, _g, _i in mt_results:
            dev = pk_to_device.get(pk)
            if not dev or dev.device_type != 'mikrotik_switch':
                continue
            for entry in arp:
                if entry.get('interface', '') == 'ether1':
                    continue
                nbr_dev = extended_ip_map.get(entry.get('ip', ''))
                if nbr_dev and nbr_dev.pk != pk and nbr_dev.device_type == 'linux':
                    edge = tuple(sorted([pk, nbr_dev.pk]))
                    edge_set.add(edge)
                    lan_connected.update([pk, nbr_dev.pk])

        # Phase 2b: Router ARP → Linux (only servers not yet connected via a switch)
        for pk, _m, arp, _g, _i in mt_results:
            dev = pk_to_device.get(pk)
            if not dev or dev.device_type != 'mikrotik_router':
                continue
            for entry in arp:
                if entry.get('interface', '') == 'ether1':
                    continue
                nbr_dev = extended_ip_map.get(entry.get('ip', ''))
                if nbr_dev and nbr_dev.pk != pk and nbr_dev.device_type == 'linux':
                    if nbr_dev.pk not in lan_connected:
                        edge = tuple(sorted([pk, nbr_dev.pk]))
                        edge_set.add(edge)
                        lan_connected.update([pk, nbr_dev.pk])

        # Phase 3: Default gateway fallback for isolated devices.
        # Uses extended_ip_map so gateway IPs like 10.1.20.1 resolve to the right router.
        gw_map = {pk: gw for pk, _m, _a, gw, _i in mt_results if gw}
        gw_map.update({pk: gw for pk, _i, gw in lx_results if gw})

        for pk in sorted(gw_map):
            if pk in lan_connected:
                continue
            gw_dev = extended_ip_map.get(gw_map[pk])
            if gw_dev and gw_dev.pk != pk:
                edge = tuple(sorted([pk, gw_dev.pk]))
                edge_set.add(edge)
                lan_connected.add(pk)

        # Phase 4: ARP fallback for devices still isolated (e.g. SSH unreachable from inside
        # a Docker container running on the same host as the target Linux server).
        # Scans all MikroTik ARP entries, including ether1, looking for the management IP.
        isolated_pks = {d.pk for d in devices if d.pk not in lan_connected}
        for pk, _m, arp, _g, _i in mt_results:
            if not isolated_pks:
                break
            for entry in arp:
                nbr_dev = ip_to_device.get(entry.get('ip', ''))
                if nbr_dev and nbr_dev.pk in isolated_pks and nbr_dev.pk != pk:
                    edge = tuple(sorted([pk, nbr_dev.pk]))
                    edge_set.add(edge)
                    lan_connected.add(nbr_dev.pk)
                    isolated_pks.discard(nbr_dev.pk)

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
