from django.urls import path
from . import views

urlpatterns = [
    path('', views.BackupListView.as_view(), name='backup-list'),
    path('create/<int:device_pk>/', views.BackupCreateView.as_view(), name='backup-create'),
    path('diff/<int:pk1>/<int:pk2>/', views.BackupDiffView.as_view(), name='backup-diff'),
    path('<int:pk>/', views.BackupViewDetail.as_view(), name='backup-view'),
    path('<int:pk>/download/', views.BackupDownloadView.as_view(), name='backup-download'),
    path('bulk-download/', views.BackupBulkDownloadView.as_view(), name='backup-bulk-download'),
]
