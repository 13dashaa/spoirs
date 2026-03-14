import socket
import os
import time
import struct

# ─── Константы ────────────────────────────────────────────────────────────────
HOST = '0.0.0.0'
PORT = 9091
PAYLOAD_SIZE = 1400
WINDOW_SIZE = 64     # Оптимальное окно (слишком большое убивает производительность)
TIMEOUT = 0.2        # Уменьшили таймаут для более быстрой реакции

PACKET_TYPE_START = 0x01
PACKET_TYPE_DATA = 0x02
PACKET_TYPE_ACK = 0x03
PACKET_TYPE_END = 0x04
PACKET_TYPE_ERROR = 0x05

def run_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    print(f"[UDP SERVER] Слушаю на {HOST}:{PORT}")

    while True:
        try:
            message, addr = sock.recvfrom(1024)
            packet_type, filename = struct.unpack(f">B{len(message)-1}s", message)
            filename = filename.decode().strip()
            filepath = os.path.join("server_files", os.path.basename(filename))

            if not os.path.exists(filepath):
                sock.sendto(struct.pack(">B", PACKET_TYPE_ERROR), addr)
                continue

            with open(filepath, 'rb') as f:
                data = f.read()

            packets = [struct.pack(">BI", PACKET_TYPE_DATA, i) + data[i*PAYLOAD_SIZE:(i+1)*PAYLOAD_SIZE]
                       for i in range((len(data) + PAYLOAD_SIZE - 1) // PAYLOAD_SIZE)]

            total_packets = len(packets)
            base = 0

            # --- ОСНОВНОЙ ЦИКЛ (ОПТИМИЗИРОВАН) ---
            while base < total_packets:
                # Отправляем окно
                for i in range(base, min(base + WINDOW_SIZE, total_packets)):
                    sock.sendto(packets[i], addr)
                    # КРОШЕЧНАЯ ПАУЗА чтобы не переполнять буфер ОС (да, это нужно в Python)
                    if i % 8 == 0: time.sleep(0.0001)

                sock.settimeout(TIMEOUT)
                try:
                    ack_message, _ = sock.recvfrom(5)
                    _, ack_num = struct.unpack(">BI", ack_message)
                    base = max(base, ack_num)
                except socket.timeout:
                    continue # Просто переотправляем окно в следующей итерации

            # Конец передачи
            for _ in range(3): sock.sendto(struct.pack(">BI", PACKET_TYPE_END, total_packets), addr)
            print(f"[UDP SERVER] Файл {filename} успешно передан.")

        except Exception as e:
            print(f"[UDP SERVER] Ошибка: {e}")

if __name__ == "__main__":
    os.makedirs("server_files", exist_ok=True)
    run_server()