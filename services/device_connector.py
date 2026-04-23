from abc import ABC, abstractmethod
import subprocess


class DeviceConnector(ABC):
    def __init__(self, device):
        self.device = device
        self.connection = None

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def execute_command(self, command: str) -> str:
        pass

    @abstractmethod
    def get_running_config(self) -> str:
        pass

    @abstractmethod
    def get_device_info(self) -> dict:
        pass

    @abstractmethod
    def get_interfaces(self) -> list:
        pass

    def ping_check(self) -> bool:
        try:
            result = subprocess.run(
                ['ping', '-c', '3', '-W', '2', str(self.device.ip_address)],
                capture_output=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
