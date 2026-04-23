from django.contrib import admin
from .models import ConfigBackup


@admin.register(ConfigBackup)
class ConfigBackupAdmin(admin.ModelAdmin):
    list_display = ['device', 'created_at', 'is_automatic', 'created_by']
    list_filter = ['is_automatic', 'device']
    readonly_fields = ['created_at', 'config_hash']
