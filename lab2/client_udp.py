import os
import socket, time, sys
from udp_protocol import *

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server = (sys.argv[1], DEFAULT_PORT)

print("Клиент запущен. Введите 'DOWNLOAD имя_файла' или 'EXIT'")

while True:
    cmd = input("> ").split()
    if not cmd: continue
    if cmd[0] == "EXIT": break

    if cmd[0] == "DOWNLOAD":
        filename = cmd[1]
        # Очищаем буфер перед отправкой, чтобы не ловить старые пакеты
        sock.setblocking(False)
        try:
            while True: sock.recv(4096)
        except:
            pass
        sock.setblocking(True)

        sock.sendto(f"DOWNLOAD {filename}".encode(), server)
        resp, _ = sock.recvfrom(1024)

        # Теперь безопасный парсинг
        parts = resp.decode().split()
        if len(parts) < 2 or parts[0] != "SIZE":
            print(f"Ошибка сервера или пустой ответ: {resp.decode()}")
            continue
        size = int(parts[1])

        print(f"[CLIENT] Скачиваю {filename} ({size} байт)...")
        start = time.monotonic()

        receiver = SlidingWindowReceiver(sock, server, size)
        data = receiver.receive()

        elapsed = time.monotonic() - start
        bitrate = (len(data) / 1024) / elapsed

        with open(f"down_{filename}", "wb") as f:
            f.write(data)
        print(f"[CLIENT] Готово! Время: {elapsed:.2f} сек. Скорость: {bitrate:.2f} КБ/с")
    if cmd[0] == "UPLOAD":
        filename = cmd[1]
        filepath = os.path.join(".", filename)
        if not os.path.exists(filepath):
            print("Файл не найден")
            continue

        data = open(filepath, "rb").read()
        size = len(data)

        # Отправляем команду и размер
        sock.sendto(f"UPLOAD {filename} {size}".encode(), server)

        # Ждем READY
        resp, _ = sock.recvfrom(1024)
        if resp == b"READY":
            print(f"[CLIENT] Отправляю {filename} ({size} байт)...")
            start = time.monotonic()

            sender = SlidingWindowSender(sock, server)
            sender.send(data)

            elapsed = time.monotonic() - start
            print(f"[CLIENT] Успешно! Скорость: {(size / 1024) / elapsed:.2f} КБ/с")