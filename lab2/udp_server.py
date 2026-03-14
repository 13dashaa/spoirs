"""
Лабораторная работа №2 — UDP Сервер
Реализует надежную передачу файла клиенту с использованием скользящего окна.
"""
import socket
import os
import time
import struct
from collections import deque

# ─── Константы ────────────────────────────────────────────────────────────────
HOST = '0.0.0.0'
PORT = 9091
PAYLOAD_SIZE = 1400  # Размер полезной нагрузки, чтобы пакет влезал в стандартный MTU
WINDOW_SIZE = 64  # Размер окна для отправки
TIMEOUT = 0.5  # Таймаут для повторной отправки окна (в секундах)
FILES_DIR = "server_files"  # Та же папка, что и у TCP сервера

# Типы пакетов
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
            # Ожидаем запрос на скачивание файла
            message, addr = sock.recvfrom(1024)
            packet_type, filename = struct.unpack(f">B{len(message) - 1}s", message)
            filename = filename.decode().strip()

            if packet_type != PACKET_TYPE_START:
                continue

            print(f"[UDP SERVER] Запрос на файл '{filename}' от {addr}")

            filepath = os.path.join(FILES_DIR, os.path.basename(filename))

            if not os.path.exists(filepath):
                print(f"[UDP SERVER] Файл не найден: {filepath}")
                error_packet = struct.pack(">B", PACKET_TYPE_ERROR)
                sock.sendto(error_packet, addr)
                continue

            # --- Подготовка к передаче ---
            with open(filepath, 'rb') as f:
                data = f.read()

            packets = []
            seq_num = 0
            while seq_num * PAYLOAD_SIZE < len(data):
                chunk = data[seq_num * PAYLOAD_SIZE: (seq_num + 1) * PAYLOAD_SIZE]
                header = struct.pack(">BI", PACKET_TYPE_DATA, seq_num)
                packets.append(header + chunk)
                seq_num += 1

            total_packets = len(packets)
            print(f"[UDP SERVER] Файл разбит на {total_packets} пакетов")

            # --- Основной цикл передачи со скользящим окном ---
            base = 0
            next_seq_num = 0
            last_ack_time = time.monotonic()

            while base < total_packets:
                # Отправляем пакеты в пределах окна
                while next_seq_num < base + WINDOW_SIZE and next_seq_num < total_packets:
                    sock.sendto(packets[next_seq_num], addr)
                    next_seq_num += 1

                # Ждем ACK или таймаут
                sock.settimeout(TIMEOUT)
                try:
                    ack_message, _ = sock.recvfrom(5)
                    ack_type, ack_num = struct.unpack(">BI", ack_message)

                    if ack_type == PACKET_TYPE_ACK:
                        # Сдвигаем базу окна
                        base = max(base, ack_num)
                        last_ack_time = time.monotonic()
                except socket.timeout:
                    print(f"[UDP SERVER] Таймаут! Повторная отправка окна с пакета {base}")
                    # Повторно отправляем всё окно
                    next_seq_num = base

            # --- Завершение передачи ---
            for _ in range(5):  # Отправляем END несколько раз для надежности
                end_packet = struct.pack(">BI", PACKET_TYPE_END, total_packets)
                sock.sendto(end_packet, addr)
                time.sleep(0.01)

            print(f"[UDP SERVER] Передача файла '{filename}' для {addr} завершена.")

        except Exception as e:
            print(f"[UDP SERVER] Произошла ошибка: {e}")


if __name__ == "__main__":
    os.makedirs(FILES_DIR, exist_ok=True)
    run_server()