"""
Лабораторная работа №1 — TCP Сервер
Поддерживает команды: ECHO, TIME, CLOSE, UPLOAD, DOWNLOAD
Один поток, последовательный сервер с поддержкой докачки файлов.
"""
import socket
import os
import datetime
import hashlib
import struct
import time

# ─── Константы ────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"  # Слушать на всех интерфейсах
PORT = 9090
BUFFER_SIZE = 4096
FILES_DIR = "server_files"  # Папка для хранения файлов на сервере
SESSIONS_DIR = "sessions"  # Папка для хранения данных о незавершенных передачах

# Параметры Keepalive (в секундах)
KEEPALIVE_IDLE = 10  # Время бездействия перед отправкой первой пробы
KEEPALIVE_INTERVAL = 5  # Интервал между пробами
KEEPALIVE_COUNT = 3  # Количество проб до разрыва соединения


# ─── Инициализация и настройка ────────────────────────────────────────────────
def ensure_directories():
    """Создает необходимые директории, если их нет."""
    os.makedirs(FILES_DIR, exist_ok=True)
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def create_server_socket():
    """Создает, настраивает и возвращает серверный сокет."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Позволяет повторно использовать адрес сразу после закрытия сокета
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(5)
    print(f"[SERVER] Слушаю на {HOST}:{PORT}")
    return s


def configure_keepalive(conn):
    """Настраивает параметры TCP Keepalive для сокета."""
    try:
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Следующие опции могут быть недоступны на некоторых ОС (например, macOS)
        if hasattr(socket, "TCP_KEEPIDLE"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_IDLE)
        if hasattr(socket, "TCP_KEEPINTVL"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVAL)
        if hasattr(socket, "TCP_KEEPCNT"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_COUNT)
    except OSError as e:
        print(f"[SERVER] Не удалось настроить TCP Keepalive: {e}")


# ─── Вспомогательные функции для работы с сокетом ──────────────────────────────
def recv_line(conn):
    """Читает строку из сокета, заканчивающуюся на \\n."""
    buf = b""
    while True:
        ch = conn.recv(1)
        if not ch or ch == b"\n":
            break
        buf += ch
    return buf.rstrip(b"\r").decode(errors="replace") if buf else None


def send_line(conn, text):
    """Отправляет строку в сокет, добавляя \\r\\n."""
    conn.sendall((text + "\r\n").encode())


def recv_exact(conn, n):
    """Читает ровно n байт из сокета."""
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Соединение закрыто во время чтения")
        data += chunk
    return data


# ─── Управление сессиями для докачки ────────────────────────────────────────────
def get_session_path(client_id, operation_id):
    """Генерирует уникальный путь к файлу сессии."""
    safe_id = hashlib.md5(f"{client_id}:{operation_id}".encode()).hexdigest()
    return os.path.join(SESSIONS_DIR, safe_id + ".session")


def load_session(client_id, operation_id):
    """Загружает смещение (offset) из файла сессии."""
    path = get_session_path(client_id, operation_id)
    return int(open(path).read().strip()) if os.path.exists(path) else 0


def save_session(client_id, operation_id, offset):
    """Сохраняет смещение в файл сессии."""
    with open(get_session_path(client_id, operation_id), "w") as f:
        f.write(str(offset))


def delete_session(client_id, operation_id):
    """Удаляет файл сессии после успешного завершения."""
    path = get_session_path(client_id, operation_id)
    if os.path.exists(path):
        os.remove(path)


# ─── Обработчики команд ────────────────────────────────────────────────────────
def handle_upload(conn, args, client_id):
    """Обрабатывает загрузку файла на сервер."""
    if not args:
        send_line(conn, "ERROR: укажите имя файла")
        return

    filename = os.path.basename(args)
    filepath = os.path.join(FILES_DIR, filename)
    operation_id = "upload:" + filename

    offset = load_session(client_id, operation_id)
    send_line(conn, f"OFFSET {offset}")

    total_size = struct.unpack(">Q", recv_exact(conn, 8))[0]

    start_time = time.monotonic()
    received = offset

    mode = "ab" if offset > 0 else "wb"
    try:
        with open(filepath, mode) as f:
            while received < total_size:
                chunk = conn.recv(min(BUFFER_SIZE, total_size - received))
                if not chunk:
                    raise ConnectionError("Обрыв во время UPLOAD")
                f.write(chunk)
                received += len(chunk)

        elapsed = time.monotonic() - start_time or 0.001
        bitrate = (total_size - offset) / elapsed / 1024
        delete_session(client_id, operation_id)
        send_line(conn, f"OK размер={total_size} скорость={bitrate:.1f} КБ/с")
    except ConnectionError as e:
        save_session(client_id, operation_id, received)
        raise e  # Передаем ошибку выше для логирования


def handle_download(conn, args, client_id):
    """Обрабатывает скачивание файла с сервера."""
    if not args:
        send_line(conn, "ERROR: укажите имя файла")
        return

    filename = os.path.basename(args)
    filepath = os.path.join(FILES_DIR, filename)

    if not os.path.exists(filepath):
        send_line(conn, "ERROR: файл не найден")
        return

    total_size = os.path.getsize(filepath)
    offset = int(recv_line(conn).split()[1])

    send_line(conn, f"SIZE {total_size}")

    start_time = time.monotonic()

    with open(filepath, "rb") as f:
        f.seek(offset)
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            conn.sendall(chunk)

    elapsed = time.monotonic() - start_time or 0.001
    bitrate = (total_size - offset) / elapsed / 1024
    print(f"[SERVER] DOWNLOAD {filename} завершён, скорость {bitrate:.1f} КБ/с")


# ─── Основной цикл обработки клиента ──────────────────────────────────────────
def handle_client(conn, addr):
    client_id = addr[0]
    print(f"[SERVER] Подключён {client_id} с порта {addr[1]}")
    configure_keepalive(conn)
    send_line(conn, "Привет! Команды: ECHO, TIME, UPLOAD, DOWNLOAD, CLOSE")

    try:
        while True:
            line = recv_line(conn)
            if line is None:
                print(f"[SERVER] {client_id} отключился (чистое закрытие)")
                break

            print(f"[SERVER] {client_id} -> {line!r}")

            parts = line.strip().split(None, 1)
            cmd = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "ECHO":
                send_line(conn, args)
            elif cmd == "TIME":
                send_line(conn, datetime.datetime.now().isoformat())
            elif cmd in ("CLOSE", "EXIT", "QUIT"):
                send_line(conn, "BYE")
                break
            elif cmd == "UPLOAD":
                handle_upload(conn, args, client_id)
            elif cmd == "DOWNLOAD":
                handle_download(conn, args, client_id)
            else:
                send_line(conn, f"ERROR: неизвестная команда '{cmd}'")

    except (ConnectionError, OSError) as e:
        print(f"[SERVER] Ошибка соединения с {client_id}: {e}")
    finally:
        conn.close()
        print(f"[SERVER] Соединение с {client_id} закрыто")


# ─── Главная функция ─────────────────────────────────────────────────────────
def main():
    ensure_directories()
    server_sock = create_server_socket()

    try:
        while True:
            # Принимаем нового клиента и обрабатываем его полностью перед тем, как принять следующего
            conn, addr = server_sock.accept()
            handle_client(conn, addr)
    except KeyboardInterrupt:
        print("\n[SERVER] Остановлен по команде пользователя")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()