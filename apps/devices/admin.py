from django.contrib import admin
from .models import Device, CommandLog


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['name', 'device_type', 'ip_address', 'status', 'location', 'last_seen']
    list_filter = ['device_type', 'status']
    search_fields = ['name', 'ip_address', 'location']


@admin.register(CommandLog)
class CommandLogAdmin(admin.ModelAdmin):
    list_display = ['device', 'command', 'user', 'executed_at', 'success']
    list_filter = ['success', 'device']
    readonly_fields = ['executed_at']
