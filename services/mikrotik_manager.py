import paramiko
from .device_connector import DeviceConnector


class MikroTikManager(DeviceConnector):
    def connect(self):
        self.connection = paramiko.SSHClient()
        self.connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connection.connect(
            hostname=str(self.device.ip_address),
            port=self.device.ssh_port,
            username=self.device.username,
            password=self.device.password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute_command(self, command: str) -> str:
        if not self.connection:
            raise ConnectionError("Не подключено к устройству")
        stdin, stdout, stderr = self.connection.exec_command(command, timeout=15)
        output = stdout.read().decode('utf-8', errors='replace')
        errors = stderr.read().decode('utf-8', errors='replace')
        return output if output.strip() else errors

    def get_running_config(self) -> str:
        return self.execute_command('/export')

    def get_device_info(self) -> dict:
        identity = self.execute_command('/system identity print')
        resource = self.execute_command('/system resource print')
        routerboard = self.execute_command('/system routerboard print')

        info = {
            'os_version': '',
            'model': 'MikroTik CHR',
            'serial_number': '',
            'uptime': '',
            'hostname': '',
        }

        for line in identity.splitlines():
            if 'name:' in line.lower():
                info['hostname'] = line.split(':', 1)[-1].strip()

        for line in resource.splitlines():
            line_lower = line.lower()
            if 'version:' in line_lower:
                info['os_version'] = 'RouterOS ' + line.split(':', 1)[-1].strip()
            if 'uptime:' in line_lower:
                info['uptime'] = line.split(':', 1)[-1].strip()
            if 'board-name:' in line_lower:
                info['model'] = line.split(':', 1)[-1].strip()

        for line in routerboard.splitlines():
            if 'serial-number:' in line.lower():
                info['serial_number'] = line.split(':', 1)[-1].strip()

        return info

    def get_interfaces(self) -> list:
        iface_output = self.execute_command('/interface print terse')
        ip_output = self.execute_command('/ip address print terse')

        ip_map = {}
        for line in ip_output.splitlines():
            parts = {}
            for item in line.split():
                if '=' in item:
                    k, v = item.split('=', 1)
                    parts[k] = v
            if 'interface' in parts and 'address' in parts:
                ip_map[parts['interface']] = parts['address'].split('/')[0]

        interfaces = []
        for line in iface_output.splitlines():
            if not line.strip():
                continue
            parts = {}
            for item in line.split():
                if '=' in item:
                    k, v = item.split('=', 1)
                    parts[k] = v

            if 'name' in parts:
                iface_name = parts['name']
                flags = line.split()[0] if line.split() else ''
                is_running = 'R' in flags

                interfaces.append({
                    'name': iface_name,
                    'status': 'up' if is_running else 'down',
                    'ip_address': ip_map.get(iface_name),
                    'speed': parts.get('actual-mtu', ''),
                    'description': parts.get('comment', ''),
                    'type': parts.get('type', ''),
                })

        return interfaces

    def get_cpu_usage(self) -> float:
        output = self.execute_command('/system resource print')
        for line in output.splitlines():
            if 'cpu-load:' in line.lower():
                try:
                    return float(line.split(':', 1)[-1].strip().replace('%', ''))
                except ValueError:
                    pass
        return 0.0

    def get_memory_usage(self) -> float:
        output = self.execute_command('/system resource print')
        total_mem = 0
        free_mem = 0
        for line in output.splitlines():
            line_lower = line.lower()
            if 'total-memory:' in line_lower:
                try:
                    total_mem = self._parse_memory(line.split(':', 1)[-1].strip())
                except Exception:
                    pass
            if 'free-memory:' in line_lower:
                try:
                    free_mem = self._parse_memory(line.split(':', 1)[-1].strip())
                except Exception:
                    pass

        if total_mem > 0:
            return round((1 - free_mem / total_mem) * 100, 1)
        return 0.0

    @staticmethod
    def _parse_terse_line(line: str) -> dict:
        import re
        result = {}
        for m in re.finditer(r'([\w-]+)=("(?:[^"\\]|\\.)*"|[^\s]*)', line):
            result[m.group(1)] = m.group(2).strip('"')
        return result

    def get_neighbors_structured(self) -> list:
        output = self.execute_command('/ip neighbor print terse')
        neighbors = []
        for line in output.splitlines():
            if '=' not in line:
                continue
            p = self._parse_terse_line(line)
            if p.get('address'):
                neighbors.append({
                    'interface': p.get('interface', ''),
                    'address':   p.get('address', ''),
                    'identity':  p.get('identity', ''),
                    'platform':  p.get('platform', ''),
                })
        return neighbors

    def get_dhcp_leases_structured(self) -> list:
        output = self.execute_command('/ip dhcp-server lease print terse')
        leases = []
        for line in output.splitlines():
            if '=' not in line:
                continue
            p = self._parse_terse_line(line)
            if not p.get('address'):
                continue
            leases.append({
                'ip': p.get('address', ''),
                'mac': p.get('mac-address', ''),
                'hostname': p.get('host-name', ''),
                'server': p.get('server', ''),
                'status': p.get('status', ''),
                'last_seen': p.get('last-seen', ''),
                'source': 'dhcp',
            })
        return leases

    def get_arp_table_structured(self) -> list:
        output = self.execute_command('/ip arp print terse')
        entries = []
        for line in output.splitlines():
            if '=' not in line:
                continue
            p = self._parse_terse_line(line)
            if not p.get('address') or not p.get('mac-address'):
                continue
            entries.append({
                'ip': p.get('address', ''),
                'mac': p.get('mac-address', ''),
                'hostname': '',
                'interface': p.get('interface', ''),
                'status': p.get('dynamic', 'no') == 'yes' and 'dynamic' or 'static',
                'last_seen': '',
                'source': 'arp',
            })
        return entries

    def _parse_memory(self, mem_str: str) -> float:
        mem_str = mem_str.strip()
        if 'MiB' in mem_str:
            return float(mem_str.replace('MiB', '')) * 1024 * 1024
        if 'GiB' in mem_str:
            return float(mem_str.replace('GiB', '')) * 1024 * 1024 * 1024
        if 'KiB' in mem_str:
            return float(mem_str.replace('KiB', '')) * 1024
        return float(mem_str)
