from django import template

register = template.Library()


@register.inclusion_tag('devices/_status_badge.html')
def device_status_badge(device):
    return {'device': device}
