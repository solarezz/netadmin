#!/bin/bash
# Резервное копирование /etc с удалённого Linux-сервера по SSH.
# Предназначен для запуска по расписанию (cron) на SRV1.
# Требует SSH-ключа без пароля: ssh-copy-id <user>@<host>
#
# Использование: backup_linux.sh <user> <host> [keep_days]
# Пример:        backup_linux.sh admin 10.1.1.102 7

set -euo pipefail

REMOTE_USER="${1:?Укажите пользователя (admin)}"
REMOTE_HOST="${2:?Укажите IP-адрес сервера}"
KEEP_DAYS="${3:-7}"

BACKUP_DIR="/opt/netadmin/backups/linux"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="${BACKUP_DIR}/etc_${REMOTE_HOST}_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Бэкап /etc с ${REMOTE_USER}@${REMOTE_HOST}"

ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "${REMOTE_USER}@${REMOTE_HOST}" \
    "sudo tar -czf - /etc 2>/dev/null" > "${DEST}"

SIZE=$(du -sh "${DEST}" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Сохранён: ${DEST} (${SIZE})"

DELETED=$(find "${BACKUP_DIR}" -name "etc_${REMOTE_HOST}_*.tar.gz" \
    -mtime "+${KEEP_DAYS}" -print -delete | wc -l)

[ "${DELETED}" -gt 0 ] && \
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Удалено старых копий: ${DELETED}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Готово."
