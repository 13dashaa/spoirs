import socket, threading, os, time
from udp_protocol import *

FILES_DIR = "server_files"
os.makedirs(FILES_DIR, exist_ok=True)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Обязательно увеличим буферы для скорости
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16 * 1024 * 1024)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16 * 1024 * 1024)
sock.bind(('0.0.0.0', DEFAULT_PORT))

print(f"[SERVER] Запущен на {DEFAULT_PORT}")

while True:
    try:
        raw, addr = sock.recvfrom(4096)
        cmd = raw.decode().split()
        if not cmd: continue

        print(f"[SERVER] Запрос от {addr}: {cmd}")

        if cmd[0] == "DOWNLOAD":
            path = os.path.join(FILES_DIR, cmd[1])
            if os.path.exists(path):
                size = os.path.getsize(path)
                sock.sendto(f"SIZE {size}".encode(), addr)
                data = open(path, "rb").read()

                print(f"[SERVER] Начинаю передачу {cmd[1]}...")
                sender = SlidingWindowSender(sock, addr)
                sender.send(data)
                print(f"[SERVER] Передача завершена.")
            else:
                sock.sendto(b"ERROR: FILE NOT FOUND", addr)
        elif cmd[0] == "UPLOAD":
            filename = cmd[1]
            size = int(cmd[2])
            path = os.path.join(FILES_DIR, filename)

            print(f"[SERVER] Ожидаю UPLOAD {filename} ({size} байт)...")
            sock.sendto(b"READY", addr)

            # Принимаем файл
            receiver = SlidingWindowReceiver(sock, addr, size)
            data = receiver.receive()

            with open(path, "wb") as f:
                f.write(data)
            print(f"[SERVER] UPLOAD {filename} завершен.")

    except Exception as e:
        print(f"[SERVER] Ошибка: {e}")