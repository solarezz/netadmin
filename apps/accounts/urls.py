from django.urls import path
from . import views

urlpatterns = [
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/add/', views.user_create, name='user-add'),
    path('users/<int:pk>/edit/', views.user_edit, name='user-edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user-delete'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
]
