from apps.monitoring.models import Alert


def alert_count(request):
    """
    Глобально добавляет active_alerts_count во все шаблоны.
    Используется для badge в navbar.
    """
    if request.user.is_authenticated:
        count = Alert.objects.filter(is_resolved=False).count()
        return {'active_alerts_count': count}
    return {'active_alerts_count': 0}
