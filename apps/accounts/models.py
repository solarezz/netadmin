from django.db import models


class AppSetting(models.Model):
    key = models.CharField(max_length=100, unique=True, verbose_name='Ключ')
    value = models.CharField(max_length=500, verbose_name='Значение')
    description = models.CharField(max_length=300, blank=True, verbose_name='Описание')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Настройка'
        verbose_name_plural = 'Настройки'
        ordering = ['key']

    def __str__(self):
        return f'{self.key} = {self.value}'
