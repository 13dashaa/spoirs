"""
Лабораторная работа №1 — TCP Клиент
Поддерживает команды: ECHO, TIME, CLOSE, UPLOAD, DOWNLOAD
Реализовано автоматическое переподключение и докачка файлов.
"""
import socket
import os
import struct
import time

# ─── Константы ────────────────────────────────────────────────────────────────
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9090
BUFFER_SIZE = 4096
DOWNLOAD_DIR = "downloads"  # Папка для скачанных файлов
RECONNECT_TIMEOUT = 30  # Через сколько секунд бездействия спросить пользователя
RECONNECT_DELAY = 3  # Пауза между попытками переподключения


# ─── Инициализация и настройка ────────────────────────────────────────────────
def ensure_directories():
    """Создает директорию для скачивания, если ее нет."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def create_connected_socket(host, port):
    """Создает и подключает сокет, настраивает keepalive."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    s.connect((host, port))
    return s


# ─── Вспомогательные функции для работы с сокетом ──────────────────────────────
def recv_line(s):
    """Читает строку из сокета."""
    buf = b""
    while True:
        ch = s.recv(1)
        if not ch or ch == b"\n":
            break
        buf += ch
    return buf.rstrip(b"\r").decode(errors="replace") if buf else None


def send_line(s, text):
    """Отправляет строку в сокет."""
    s.sendall((text + "\r\n").encode())


# ─── Логика команд ───────────────────────────────────────────────────────────────
def do_upload(s, filepath):
    """Выполняет загрузку файла на сервер с поддержкой докачки."""
    if not os.path.exists(filepath):
        print(f"[CLIENT] Файл '{filepath}' не найден")
        return

    filename = os.path.basename(filepath)
    total_size = os.path.getsize(filepath)

    send_line(s, f"UPLOAD {filename}")

    response = recv_line(s)
    if not response or not response.startswith("OFFSET"):
        print(f"[CLIENT] Неожиданный ответ от сервера: {response}")
        return

    offset = int(response.split()[1])
    print(f"[CLIENT] Сервер готов к докачке с байта {offset} из {total_size}")

    s.sendall(struct.pack(">Q", total_size))

    start_time = time.monotonic()

    with open(filepath, "rb") as f:
        f.seek(offset)
        while (chunk := f.read(BUFFER_SIZE)):
            s.sendall(chunk)

    result = recv_line(s)
    elapsed = time.monotonic() - start_time or 0.001
    bitrate = (total_size - offset) / elapsed / 1024
    print(f"\n[CLIENT] Ответ сервера: {result}")
    print(f"[CLIENT] Эффективная скорость: {bitrate:.1f} КБ/с")


def do_download(s, filename):
    """Выполняет скачивание файла с сервера с поддержкой докачки."""
    local_path = os.path.join(DOWNLOAD_DIR, filename)
    offset = os.path.getsize(local_path) if os.path.exists(local_path) else 0

    send_line(s, f"DOWNLOAD {filename}")
    send_line(s, f"OFFSET {offset}")

    size_line = recv_line(s)
    if not size_line:
        raise ConnectionError("Сервер не ответил на запрос размера файла")
    if size_line.startswith("ERROR"):
        print(f"[CLIENT] Ошибка сервера: {size_line}")
        return

    total_size = int(size_line.split()[1])
    print(f"[CLIENT] Скачиваю '{filename}' ({total_size} байт), начиная с {offset}")

    start_time = time.monotonic()
    received = offset

    mode = "ab" if offset > 0 else "wb"
    with open(local_path, mode) as f:
        while received < total_size:
            chunk = s.recv(min(BUFFER_SIZE, total_size - received))
            if not chunk:
                raise ConnectionError("Обрыв соединения во время скачивания")
            f.write(chunk)
            received += len(chunk)

    elapsed = time.monotonic() - start_time or 0.001
    bitrate = (total_size - offset) / elapsed / 1024
    print(f"\n[CLIENT] Файл '{local_path}' скачан. Скорость: {bitrate:.1f} КБ/с")


# ─── Логика переподключения ────────────────────────────────────────────────────
def reconnect_loop(host, port):
    """Пытается переподключиться к серверу."""
    start_time = time.monotonic()
    warned = False

    while True:
        try:
            print("\r[CLIENT] Потеряно соединение. Пытаюсь переподключиться...", end="")
            new_socket = create_connected_socket(host, port)
            print("\n[CLIENT] Соединение восстановлено!")
            return new_socket
        except (socket.error, OSError):
            if not warned and time.monotonic() - start_time > RECONNECT_TIMEOUT:
                warned = True
                answer = input(
                    f"\n[CLIENT] Не удается подключиться {RECONNECT_TIMEOUT} сек. Продолжать? (y/n): ").lower()
                if answer != 'y':
                    return None
            time.sleep(RECONNECT_DELAY)


# ─── Главный интерактивный цикл ───────────────────────────────────────────────
def interactive_loop(s, host, port):
    """Основной цикл для взаимодействия с пользователем."""
    welcome_msg = recv_line(s)
    print(f"[SERVER] {welcome_msg}")

    while True:
        try:
            user_input = input("> ").strip()
            if not user_input:
                continue

            parts = user_input.split(None, 1)
            cmd = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "UPLOAD":
                do_upload(s, args)
            elif cmd == "DOWNLOAD":
                do_download(s, args)
            elif cmd in ("CLOSE", "EXIT", "QUIT"):
                send_line(s, "CLOSE")
                print(f"[SERVER] {recv_line(s)}")
                break
            else:
                send_line(s, user_input)
                response = recv_line(s)
                if response is None:
                    raise ConnectionError("Соединение разорвано сервером")
                print(f"[SERVER] {response}")

        except (ConnectionError, OSError) as e:
            print(f"\n[CLIENT] Ошибка: {e}")
            s.close()
            s = reconnect_loop(host, port)
            if s is None:
                print("[CLIENT] Не удалось восстановить соединение. Завершение работы.")
                break
            # После успешного переподключения, получаем новое приветствие
            print(f"[SERVER] {recv_line(s)}")

    return s


def main():
    ensure_directories()
    host = DEFAULT_HOST
    port = DEFAULT_PORT

    try:
        s = create_connected_socket(host, port)
    except (socket.error, OSError) as e:
        print(f"[CLIENT] Не удалось подключиться к {host}:{port}. Ошибка: {e}")
        return

    try:
        s = interactive_loop(s, host, port)
    except KeyboardInterrupt:
        print("\n[CLIENT] Прервано пользователем. Отправка команды CLOSE...")
        send_line(s, "CLOSE")
    finally:
        s.close()
        print("[CLIENT] Соединение закрыто.")


if __name__ == "__main__":
    main()