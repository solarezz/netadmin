from django.contrib import admin
from .models import DeviceMetric, Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['device', 'severity', 'message', 'is_resolved', 'created_at']
    list_filter = ['severity', 'is_resolved']


@admin.register(DeviceMetric)
class DeviceMetricAdmin(admin.ModelAdmin):
    list_display = ['device', 'cpu_usage', 'memory_usage', 'timestamp']
    list_filter = ['device']
