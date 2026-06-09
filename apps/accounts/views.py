import sys
import django

from django.contrib.auth.models import User, Group
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, TemplateView
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q

from .mixins import AdminRequiredMixin
from .models import AppSetting


DEFAULT_SETTINGS = [
    ('auto_refresh_interval', '30', 'Интервал автообновления (секунды)'),
    ('ping_timeout', '3', 'Таймаут пинга (секунды)'),
    ('offline_threshold_minutes', '5', 'Порог офлайн (минуты)'),
    ('max_command_history', '100', 'Макс. история команд на устройство'),
    ('alerts_retention_days', '30', 'Хранение алертов (дни)'),
]


def _get_role(user):
    if user.is_superuser or user.groups.filter(name='admin').exists():
        return 'admin'
    elif user.groups.filter(name='operator').exists():
        return 'operator'
    return 'viewer'


class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = 'accounts/users_list.html'
    context_object_name = 'users'

    def get_queryset(self):
        qs = User.objects.prefetch_related('groups').order_by('username')
        q = self.request.GET.get('q', '')
        role = self.request.GET.get('role', '')
        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(email__icontains=q) |
                Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )
        if role == 'admin':
            qs = qs.filter(Q(is_superuser=True) | Q(groups__name='admin'))
        elif role == 'operator':
            qs = qs.filter(groups__name='operator').exclude(
                Q(is_superuser=True) | Q(groups__name='admin')
            )
        elif role == 'viewer':
            qs = qs.exclude(
                Q(is_superuser=True) | Q(groups__name__in=['admin', 'operator'])
            )
        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_u = User.objects.prefetch_related('groups')
        ctx['count_total'] = all_u.count()
        ctx['count_admin'] = all_u.filter(
            Q(is_superuser=True) | Q(groups__name='admin')
        ).distinct().count()
        ctx['count_operator'] = all_u.filter(groups__name='operator').exclude(
            Q(is_superuser=True) | Q(groups__name='admin')
        ).distinct().count()
        ctx['count_viewer'] = all_u.exclude(
            Q(is_superuser=True) | Q(groups__name__in=['admin', 'operator'])
        ).distinct().count()
        ctx['selected_q'] = self.request.GET.get('q', '')
        ctx['selected_role'] = self.request.GET.get('role', '')
        ctx['users_with_roles'] = [(u, _get_role(u)) for u in ctx['users']]
        return ctx


@login_required
def user_create(request):
    if not (request.user.is_superuser or request.user.groups.filter(name='admin').exists()):
        messages.error(request, 'Недостаточно прав. Требуется роль admin.')
        return redirect('user-list')

    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.POST
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', 'viewer')

        if not username:
            errors['username'] = 'Обязательное поле'
        elif User.objects.filter(username=username).exists():
            errors['username'] = 'Пользователь с таким именем уже существует'
        if not password:
            errors['password'] = 'Обязательное поле'
        elif len(password) < 8:
            errors['password'] = 'Пароль должен содержать не менее 8 символов'

        if not errors:
            new_user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name,
            )
            if role in ('admin', 'operator'):
                group, _ = Group.objects.get_or_create(name=role)
                new_user.groups.add(group)
            messages.success(request, f'Пользователь «{username}» создан.')
            return redirect('user-list')

    return render(request, 'accounts/user_form.html', {
        'is_create': True,
        'errors': errors,
        'form_data': form_data,
    })


@login_required
def user_edit(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='admin').exists()):
        messages.error(request, 'Недостаточно прав. Требуется роль admin.')
        return redirect('user-list')

    target = get_object_or_404(User, pk=pk)
    current_role = _get_role(target)
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.POST
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', current_role)
        new_password = request.POST.get('new_password', '').strip()

        if new_password and len(new_password) < 8:
            errors['new_password'] = 'Пароль должен содержать не менее 8 символов'

        if not errors:
            target.first_name = first_name
            target.last_name = last_name
            target.email = email
            if new_password:
                target.set_password(new_password)
            target.save()

            target.groups.clear()
            if role in ('admin', 'operator'):
                group, _ = Group.objects.get_or_create(name=role)
                target.groups.add(group)

            messages.success(request, f'Пользователь «{target.username}» обновлён.')
            return redirect('user-list')

    return render(request, 'accounts/user_form.html', {
        'is_create': False,
        'target_user': target,
        'current_role': current_role,
        'errors': errors,
        'form_data': form_data,
    })


@login_required
def user_delete(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='admin').exists()):
        messages.error(request, 'Недостаточно прав. Требуется роль admin.')
        return redirect('user-list')

    target = get_object_or_404(User, pk=pk)

    if target == request.user:
        messages.error(request, 'Нельзя удалить собственный аккаунт.')
        return redirect('user-list')

    if request.method == 'POST':
        username = target.username
        target.delete()
        messages.success(request, f'Пользователь «{username}» удалён.')
        return redirect('user-list')

    return render(request, 'accounts/user_confirm_delete.html', {'target_user': target})


class SettingsView(AdminRequiredMixin, LoginRequiredMixin, TemplateView):
    template_name = 'accounts/settings.html'

    def _ensure_defaults(self):
        for key, value, desc in DEFAULT_SETTINGS:
            AppSetting.objects.get_or_create(key=key, defaults={'value': value, 'description': desc})

    def get_context_data(self, **kwargs):
        self._ensure_defaults()
        ctx = super().get_context_data(**kwargs)
        ctx['settings_dict'] = {s.key: s for s in AppSetting.objects.all()}
        ctx['django_version'] = '.'.join(str(v) for v in django.VERSION[:3])
        ctx['python_version'] = sys.version.split(' ')[0]
        ctx['active_tab'] = self.request.GET.get('tab', 'monitoring')
        from django.conf import settings as django_settings
        ctx['debug'] = django_settings.DEBUG
        return ctx

    def post(self, request, *args, **kwargs):
        self._ensure_defaults()
        for key, value in request.POST.items():
            if key.startswith('setting_'):
                setting_key = key[8:]
                AppSetting.objects.filter(key=setting_key).update(value=value.strip())
        messages.success(request, 'Настройки успешно сохранены.')
        return redirect('settings')
