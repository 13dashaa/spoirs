import socket, threading, os
from udp_protocol import *

FILES_DIR = "server_files"
os.makedirs(FILES_DIR, exist_ok=True)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', DEFAULT_PORT))

def handle():
    while True:
        raw, addr = sock.recvfrom(4096)
        cmd = raw.decode().split()
        if cmd[0] == "DOWNLOAD":
            path = os.path.join(FILES_DIR, cmd[1])
            size = os.path.getsize(path)
            sock.sendto(f"SIZE {size}".encode(), addr)
            data = open(path, "rb").read()
            sender = SlidingWindowSender(sock, addr)
            sender.send(data)

threading.Thread(target=handle, daemon=True).start()
input("Сервер запущен. Нажми Enter для выхода.\n")