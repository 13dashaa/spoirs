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
        sock.sendto(f"DOWNLOAD {filename}".encode(), server)
        resp, _ = sock.recvfrom(1024)

        if resp.startswith(b"ERROR"):
            print(resp.decode())
            continue

        size = int(resp.decode().split()[1])

        print(f"[CLIENT] Скачиваю {filename} ({size} байт)...")
        start = time.monotonic()

        receiver = SlidingWindowReceiver(sock, server, size)
        data = receiver.receive()

        elapsed = time.monotonic() - start
        bitrate = (len(data) / 1024) / elapsed

        with open(f"down_{filename}", "wb") as f:
            f.write(data)
        print(f"[CLIENT] Готово! Время: {elapsed:.2f} сек. Скорость: {bitrate:.2f} КБ/с")