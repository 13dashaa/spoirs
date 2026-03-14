import socket
import os
import struct

HOST = '0.0.0.0'
PORT = 9091
PAYLOAD_SIZE = 1400
WINDOW_SIZE = 256  # Увеличили окно для скорости
TIMEOUT = 0.3


def run_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024 * 4)
    sock.bind((HOST, PORT))
    print(f"[UDP SERVER] Слушаю на {HOST}:{PORT}")

    while True:
        # Ждем запрос (БЕЗ timeout, чтобы сервер не падал)
        message, addr = sock.recvfrom(1024)
        _, filename = struct.unpack(f">B{len(message) - 1}s", message)
        filepath = os.path.join("server_files", filename.decode().strip())

        if not os.path.exists(filepath):
            continue

        with open(filepath, 'rb') as f:
            data = f.read()

        packets = [struct.pack(">BI", 0x02, i) + data[i * PAYLOAD_SIZE:(i + 1) * PAYLOAD_SIZE]
                   for i in range((len(data) + PAYLOAD_SIZE - 1) // PAYLOAD_SIZE)]

        total_packets = len(packets)
        base = 0

        print(f"[UDP SERVER] Передача {filename} для {addr}")

        # Передача с таймаутом
        sock.settimeout(TIMEOUT)
        while base < total_packets:
            for i in range(base, min(base + WINDOW_SIZE, total_packets)):
                sock.sendto(packets[i], addr)

            try:
                ack_message, _ = sock.recvfrom(5)
                _, ack_num = struct.unpack(">BI", ack_message)
                base = max(base, ack_num)
            except socket.timeout:
                continue

        for _ in range(3): sock.sendto(struct.pack(">BI", 0x04, total_packets), addr)
        print(f"[UDP SERVER] Файл передан.")
        sock.settimeout(None)  # Возвращаем блокирующий режим


if __name__ == "__main__":
    os.makedirs("server_files", exist_ok=True)
    run_server()