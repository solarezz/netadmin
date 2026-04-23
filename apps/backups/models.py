import hashlib
from django.db import models


class ConfigBackup(models.Model):
    device = models.ForeignKey('devices.Device', on_delete=models.CASCADE, related_name='backups')
    config_text = models.TextField(verbose_name='Текст конфигурации')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    is_automatic = models.BooleanField(default=False, verbose_name='Автоматический')
    config_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Бэкап конфигурации'
        verbose_name_plural = 'Бэкапы конфигураций'

    def save(self, *args, **kwargs):
        self.config_hash = hashlib.sha256(self.config_text.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.device.name} — {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def size_kb(self):
        return round(len(self.config_text.encode()) / 1024, 1)
