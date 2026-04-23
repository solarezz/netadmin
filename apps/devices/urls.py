from django.urls import path
from . import views

urlpatterns = [
    path('', views.DeviceListView.as_view(), name='device-list'),
    path('add/', views.DeviceCreateView.as_view(), name='device-add'),
    path('<int:pk>/', views.DeviceDetailView.as_view(), name='device-detail'),
    path('<int:pk>/edit/', views.DeviceUpdateView.as_view(), name='device-edit'),
    path('<int:pk>/delete/', views.DeviceDeleteView.as_view(), name='device-delete'),
    path('<int:pk>/execute/', views.DeviceExecuteView.as_view(), name='device-execute'),
    path('api/test-connection/', views.TestConnectionView.as_view(), name='test-connection'),
    path('<int:pk>/connected/', views.ConnectedDevicesView.as_view(), name='device-connected'),
]
