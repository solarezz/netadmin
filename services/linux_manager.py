import paramiko
from .device_connector import DeviceConnector


class LinuxManager(DeviceConnector):
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
        return output + errors if errors else output

    def get_running_config(self) -> str:
        timestamp = self.execute_command('date +%Y%m%d_%H%M%S').strip()
        archive = f'/tmp/etc_backup_{timestamp}.tar.gz'

        # Создаём архив /etc (без sudo — большинство файлов читаются обычным пользователем)
        self.execute_command(f'tar -czf {archive} /etc 2>/dev/null; true')
        size = self.execute_command(f'du -sh {archive} 2>/dev/null | cut -f1').strip()

        lines = []
        if size:
            lines.append(f'# Архив /etc: {archive}')
            lines.append(f'# Размер: {size}  |  Создан: {timestamp}')
            lines.append(f'# Сервер: {self.device.ip_address} ({self.device.name})')
            lines.append('')

        # Всегда добавляем текст ключевых файлов для diff в веб-интерфейсе
        config_files = [
            ('/etc/hostname',          'Hostname'),
            ('/etc/hosts',             'Hosts'),
            ('/etc/netplan/*.yaml',    'Netplan'),
            ('/etc/network/interfaces','Network interfaces'),
            ('/etc/ssh/sshd_config',   'SSH config'),
            ('/etc/fstab',             'Fstab'),
            ('/etc/crontab',           'Crontab'),
        ]
        for path, label in config_files:
            content = self.execute_command(f'cat {path} 2>/dev/null')
            if content.strip():
                lines.append(f'### {label} ({path}) ###')
                lines.append(content)
                lines.append('')

        return '\n'.join(lines) if lines else 'Конфигурационные файлы не найдены'

    def get_device_info(self) -> dict:
        return {
            'os_version': self.execute_command(
                'cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2'
            ).strip().strip('"'),
            'model': self.execute_command(
                'cat /sys/class/dmi/id/product_name 2>/dev/null || echo "Virtual Machine"'
            ).strip(),
            'serial_number': self.execute_command(
                'cat /sys/class/dmi/id/product_serial 2>/dev/null || echo "N/A"'
            ).strip(),
            'uptime': self.execute_command('uptime -p').strip(),
            'hostname': self.execute_command('hostname').strip(),
        }

    def get_interfaces(self) -> list:
        output = self.execute_command("ip -o addr show | awk '{print $2, $3, $4}'")
        interfaces = []
        seen = set()
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] not in seen:
                seen.add(parts[0])
                ip = parts[2].split('/')[0] if '/' in parts[2] else parts[2]
                interfaces.append({
                    'name': parts[0],
                    'status': 'up',
                    'ip_address': ip,
                    'speed': '',
                    'description': '',
                })
        return interfaces

    def get_cpu_usage(self) -> float:
        # base64-encoded Python script — избегаем проблем с кавычками в SSH
        import base64
        script = (
            "import time\n"
            "with open('/proc/stat') as f: a=f.readline().split()\n"
            "time.sleep(0.5)\n"
            "with open('/proc/stat') as f: b=f.readline().split()\n"
            "tot=sum(int(x) for x in b[1:])-sum(int(x) for x in a[1:])\n"
            "idl=int(b[4])-int(a[4])\n"
            "print(round(100*(1-idl/tot),1) if tot else 0)\n"
        )
        encoded = base64.b64encode(script.encode()).decode()
        output = self.execute_command(f"echo {encoded} | base64 -d | python3")
        try:
            val = float(output.strip())
            return val if val >= 0 else None
        except (ValueError, TypeError):
            return None

    def get_memory_usage(self) -> float:
        output = self.execute_command(
            "free | grep Mem | awk '{printf \"%.1f\", $3/$2 * 100.0}'"
        )
        try:
            return float(output.strip())
        except ValueError:
            return 0.0
