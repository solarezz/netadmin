import hashlib
import difflib
from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from .models import ConfigBackup
from apps.devices.models import Device
from services import get_connector


class BackupListView(LoginRequiredMixin, ListView):
    model = ConfigBackup
    template_name = 'backups/backup_list.html'
    context_object_name = 'backups'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.GET.get('device')
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['devices'] = Device.objects.all()
        ctx['selected_device'] = self.request.GET.get('device', '')
        return ctx


class BackupCreateView(LoginRequiredMixin, View):
    def post(self, request, device_pk):
        device = get_object_or_404(Device, pk=device_pk)
        try:
            connector = get_connector(device)
            with connector:
                config = connector.get_running_config()

            new_hash = hashlib.sha256(config.encode()).hexdigest()
            last_backup = device.backups.first()

            if last_backup and last_backup.config_hash == new_hash:
                messages.info(request, f'Конфигурация {device.name} не изменилась с последнего бэкапа')
            else:
                ConfigBackup.objects.create(
                    device=device, config_text=config,
                    created_by=request.user, is_automatic=False,
                )
                messages.success(request, f'Бэкап {device.name} успешно создан')
        except Exception as e:
            messages.error(request, f'Ошибка подключения к {device.name}: {e}')

        return redirect('device-detail', pk=device.pk)


class BackupDiffView(LoginRequiredMixin, View):
    def get(self, request, pk1, pk2):
        backup1 = get_object_or_404(ConfigBackup, pk=pk1)
        backup2 = get_object_or_404(ConfigBackup, pk=pk2)

        diff = list(difflib.unified_diff(
            backup1.config_text.splitlines(),
            backup2.config_text.splitlines(),
            fromfile=f'Бэкап от {backup1.created_at.strftime("%Y-%m-%d %H:%M")}',
            tofile=f'Бэкап от {backup2.created_at.strftime("%Y-%m-%d %H:%M")}',
            lineterm='',
        ))

        return render(request, 'backups/backup_diff.html', {
            'backup1': backup1,
            'backup2': backup2,
            'diff_lines': diff,
        })


class BackupViewDetail(LoginRequiredMixin, View):
    def get(self, request, pk):
        backup = get_object_or_404(ConfigBackup, pk=pk)
        return render(request, 'backups/backup_view.html', {'backup': backup})
