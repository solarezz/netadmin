from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect


class OperatorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        return u.is_superuser or u.groups.filter(name__in=['operator', 'admin']).exists()

    def handle_no_permission(self):
        messages.error(self.request, 'Недостаточно прав. Требуется роль operator или admin.')
        return redirect('device-list')
