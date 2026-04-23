from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


USERS = [
    {'username': 'admin',    'password': 'Admin2024!',    'group': 'admin',    'is_superuser': True},
    {'username': 'operator', 'password': 'Operator2024!', 'group': 'operator', 'is_superuser': False},
    {'username': 'viewer',   'password': 'Viewer2024!',   'group': 'viewer',   'is_superuser': False},
]


class Command(BaseCommand):
    help = 'Создаёт группы viewer/operator/admin и тестовых пользователей'

    def handle(self, *args, **kwargs):
        for name in ('viewer', 'operator', 'admin'):
            Group.objects.get_or_create(name=name)
        self.stdout.write('Группы созданы: viewer, operator, admin')

        for u in USERS:
            user, created = User.objects.get_or_create(username=u['username'])
            user.set_password(u['password'])
            user.is_superuser = u['is_superuser']
            user.is_staff = u['is_superuser']
            user.save()

            group = Group.objects.get(name=u['group'])
            user.groups.set([group])

            action = 'Создан' if created else 'Обновлён'
            self.stdout.write(f'{action}: {u["username"]} / {u["password"]} [{u["group"]}]')
