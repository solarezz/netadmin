from django.db import models


class DeviceMetric(models.Model):
    device = models.ForeignKey('devices.Device', on_delete=models.CASCADE, related_name='metrics')
    timestamp = models.DateTimeField(auto_now_add=True)
    cpu_usage = models.FloatField(null=True, blank=True, verbose_name='CPU %')
    memory_usage = models.FloatField(null=True, blank=True, verbose_name='RAM %')
    extra_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['device', '-timestamp'])]
        verbose_name = 'Метрика'
        verbose_name_plural = 'Метрики'


class Alert(models.Model):
    class Severity(models.TextChoices):
        INFO = 'info', 'Информация'
        WARNING = 'warning', 'Предупреждение'
        CRITICAL = 'critical', 'Критический'

    device = models.ForeignKey('devices.Device', on_delete=models.CASCADE, related_name='alerts')
    severity = models.CharField(max_length=10, choices=Severity.choices)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Алерт'
        verbose_name_plural = 'Алерты'

    def __str__(self):
        return f"[{self.severity}] {self.device.name}: {self.message[:50]}"
