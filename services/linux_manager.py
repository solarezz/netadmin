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
        configs = []
        config_files = [
            ('/etc/hostname', 'Hostname'),
            ('/etc/netplan/*.yaml', 'Netplan (сеть)'),
            ('/etc/network/interfaces', 'Network interfaces'),
            ('/etc/ssh/sshd_config', 'SSH config'),
            ('/etc/fstab', 'Disk mounts'),
        ]
        for path, label in config_files:
            output = self.execute_command(f'cat {path} 2>/dev/null')
            if output.strip():
                configs.append(f"### {label} ({path}) ###\n{output}")
        return '\n\n'.join(configs) if configs else "Конфигурационные файлы не найдены"

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
        # Два замера /proc/stat с паузой 1 сек — надёжно на любом Linux
        cmd = (
            "python3 -c \""
            "import time; "
            "f=open('/proc/stat'); l1=f.readline(); f.close(); "
            "time.sleep(1); "
            "f=open('/proc/stat'); l2=f.readline(); f.close(); "
            "a=[int(x) for x in l1.split()[1:]]; "
            "b=[int(x) for x in l2.split()[1:]]; "
            "t1=sum(a); i1=a[3]; t2=sum(b); i2=b[3]; "
            "print(round(100*(1-(i2-i1)/(t2-t1)),1)) if t2!=t1 else print(0)\""
        )
        output = self.execute_command(cmd)
        try:
            return float(output.strip())
        except ValueError:
            # Запасной вариант: vmstat
            try:
                out2 = self.execute_command("vmstat 1 2 | tail -1 | awk '{print 100-$15}'")
                return float(out2.strip())
            except Exception:
                return 0.0

    def get_memory_usage(self) -> float:
        output = self.execute_command(
            "free | grep Mem | awk '{printf \"%.1f\", $3/$2 * 100.0}'"
        )
        try:
            return float(output.strip())
        except ValueError:
            return 0.0
