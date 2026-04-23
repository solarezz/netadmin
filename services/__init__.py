def get_connector(device):
    from .mikrotik_manager import MikroTikManager
    from .linux_manager import LinuxManager

    connectors = {
        'mikrotik_router': MikroTikManager,
        'mikrotik_switch': MikroTikManager,
        'linux': LinuxManager,
    }

    connector_class = connectors.get(device.device_type)
    if not connector_class:
        raise ValueError(f"Неизвестный тип устройства: {device.device_type}")

    return connector_class(device)
