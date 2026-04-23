from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('check-all/', views.CheckAllDevicesView.as_view(), name='check-all-devices'),
    path('alerts/<int:alert_id>/resolve/', views.ResolveAlertView.as_view(), name='alert-resolve'),
    path('api/devices/status/', views.DeviceStatusApiView.as_view(), name='api-devices-status'),
    path('api/devices/<int:pk>/metrics/', views.DeviceMetricsApiView.as_view(), name='api-device-metrics'),
    path('topology/', views.TopologyView.as_view(), name='topology'),
    path('api/topology/', views.TopologyApiView.as_view(), name='api-topology'),
]
