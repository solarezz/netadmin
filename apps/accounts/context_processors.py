def user_role(request):
    if not request.user.is_authenticated:
        return {'user_role': '', 'is_operator': False}
    u = request.user
    if u.is_superuser or u.groups.filter(name='admin').exists():
        role = 'admin'
    elif u.groups.filter(name='operator').exists():
        role = 'operator'
    else:
        role = 'viewer'
    return {
        'user_role': role,
        'is_operator': role in ('operator', 'admin'),
    }
