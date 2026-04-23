import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed


def ping_host(ip_address: str, count: int = 3, timeout: int = 2) -> dict:
    try:
        if platform.system() == 'Windows':
            cmd = ['ping', '-n', str(count), '-w', str(timeout * 1000), str(ip_address)]
        else:
            cmd = ['ping', '-c', str(count), '-W', str(timeout), str(ip_address)]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=count * timeout + 5
        )
        alive = result.returncode == 0
        rtt = None
        packet_loss = 100.0

        for line in result.stdout.splitlines():
            if 'avg' in line and '/' in line:
                try:
                    rtt = float(line.split('/')[4])
                except (IndexError, ValueError):
                    pass
            if 'packet loss' in line or 'Lost' in line:
                try:
                    packet_loss = float(line.split('%')[0].split()[-1])
                except (IndexError, ValueError):
                    packet_loss = 0.0 if alive else 100.0

        return {'ip': ip_address, 'alive': alive, 'rtt_ms': rtt, 'packet_loss': packet_loss}
    except Exception:
        return {'ip': ip_address, 'alive': False, 'rtt_ms': None, 'packet_loss': 100.0}


def ping_multiple(ip_list: list, max_workers: int = 10) -> list:
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(ping_host, ip): ip for ip in ip_list}
        for future in as_completed(futures):
            results.append(future.result())
    return results
