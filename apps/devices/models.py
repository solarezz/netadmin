from django.db import models


class DeviceType(models.TextChoices):
    MIKROTIK_ROUTER = 'mikrotik_router', 'MikroTik Router'
    MIKROTIK_SWITCH = 'mikrotik_switch', 'MikroTik Switch'
    LINUX = 'linux', 'Linux Server'


class DeviceStatus(models.TextChoices):
    ONLINE = 'online', 'Online'
    OFFLINE = 'offline', 'Offline'
    WARNING = 'warning', 'Warning'
    UNKNOWN = 'unknown', 'Unknown'


class Device(models.Model):
    name = models.CharField(max_length=100, verbose_name='Имя устройства')
    device_type = models.CharField(max_length=20, choices=DeviceType.choices, verbose_name='Тип')
    ip_address = models.GenericIPAddressField(unique=True, verbose_name='IP-адрес управления')

    ssh_port = models.PositiveIntegerField(default=22)
    username = models.CharField(max_length=50, verbose_name='Логин')
    password = models.CharField(max_length=128, verbose_name='Пароль')

    location = models.CharField(max_length=100, blank=True, verbose_name='Расположение')
    description = models.TextField(blank=True, verbose_name='Описание')

    status = models.CharField(max_length=10, choices=DeviceStatus.choices,
                               default=DeviceStatus.UNKNOWN, verbose_name='Статус')
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name='Последний ответ')
    uptime = models.CharField(max_length=100, blank=True, verbose_name='Uptime')

    os_version = models.CharField(max_length=200, blank=True, verbose_name='Версия ОС')
    serial_number = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True, verbose_name='Модель')

    serviced_at = models.DateField(null=True, blank=True, verbose_name='Дата обслуживания')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Устройство'
        verbose_name_plural = 'Устройства'

    def __str__(self):
        return f"{self.name} ({self.ip_address})"

    def get_status_color(self):
        colors = {
            'online': 'success',
            'offline': 'danger',
            'warning': 'warning',
            'unknown': 'secondary',
        }
        return colors.get(self.status, 'secondary')


class CommandLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='command_logs')
    command = models.TextField(verbose_name='Команда')
    output = models.TextField(verbose_name='Результат')
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    executed_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)

    class Meta:
        ordering = ['-executed_at']
        verbose_name = 'Лог команды'
        verbose_name_plural = 'Лог команд'

    def __str__(self):
        return f"{self.device.name}: {self.command[:50]}"
