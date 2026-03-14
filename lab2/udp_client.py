"""
Лабораторная работа №2 — UDP Клиент
Скачивает файл с сервера, используя надежный протокол со скользящим окном.
"""
import socket
import os
import struct
import time

# ─── Константы ────────────────────────────────────────────────────────────────
SERVER_HOST = "192.168.10.102"
SERVER_PORT = 9091
BUFFER_SIZE = 2048  # Буфер должен вмещать самый большой пакет
DOWNLOAD_DIR = "downloads"
CLIENT_TIMEOUT = 10.0  # Сколько ждать ответа от сервера в целом

# Типы пакетов (должны совпадать с серверными)
PACKET_TYPE_START = 0x01
PACKET_TYPE_DATA = 0x02
PACKET_TYPE_ACK = 0x03
PACKET_TYPE_END = 0x04
PACKET_TYPE_ERROR = 0x05


def run_client(filename_to_download):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Увеличиваем буфер приема до 2 МБ
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024 * 2)
    sock.settimeout(CLIENT_TIMEOUT)
    try:
        # 1. Отправляем запрос на файл
        start_packet = struct.pack(f">B{len(filename_to_download)}s", PACKET_TYPE_START, filename_to_download.encode())
        sock.sendto(start_packet, (SERVER_HOST, SERVER_PORT))
        print(f"[UDP CLIENT] Запрос на скачивание '{filename_to_download}' отправлен.")

        # 2. Получаем пакеты и собираем файл
        received_chunks = {}
        expected_seq_num = 0
        total_packets = -1
        start_time = time.monotonic()

        while True:
            packet, _ = sock.recvfrom(BUFFER_SIZE)
            packet_type = packet[0]

            if packet_type == PACKET_TYPE_DATA:
                _, seq_num = struct.unpack(">BI", packet[:5])
                data = packet[5:]

                if seq_num >= expected_seq_num:
                    received_chunks[seq_num] = data

                # Собираем полученные по порядку чанки
                while expected_seq_num in received_chunks:
                    expected_seq_num += 1

                # Отправляем кумулятивный ACK
                ack_packet = struct.pack(">BI", PACKET_TYPE_ACK, expected_seq_num)
                sock.sendto(ack_packet, (SERVER_HOST, SERVER_PORT))

            elif packet_type == PACKET_TYPE_END:
                _, total_packets = struct.unpack(">BI", packet)
                print("[UDP CLIENT] Получен сигнал о завершении передачи.")
                break  # Выходим из цикла приема

            elif packet_type == PACKET_TYPE_ERROR:
                print("[UDP CLIENT] Сервер сообщил, что файл не найден.")
                return

        # 3. Собираем и сохраняем файл
        if total_packets == -1 or len(received_chunks) != total_packets:
            print(
                f"[UDP CLIENT] Ошибка: получено {len(received_chunks)} из {total_packets} пакетов. Файл может быть поврежден.")

        # Сортируем чанки по номеру и записываем в файл
        full_data = b"".join(received_chunks[i] for i in sorted(received_chunks.keys()))

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        local_path = os.path.join(DOWNLOAD_DIR, os.path.basename(filename_to_download))

        with open(local_path, 'wb') as f:
            f.write(full_data)

        end_time = time.monotonic()
        duration = end_time - start_time
        bitrate_mbps = (len(full_data) * 8) / (duration * 1_000_000) if duration > 0 else 0

        print(f"[UDP CLIENT] Файл сохранен в '{local_path}'")
        print(f"[UDP CLIENT] Размер: {len(full_data) / 1024:.2f} КБ")
        print(f"[UDP CLIENT] Время: {duration:.2f} сек")
        print(f"[UDP CLIENT] Скорость: {bitrate_mbps:.2f} Мбит/с")

    except socket.timeout:
        print("[UDP CLIENT] Сервер не отвечает. Завершение работы.")
    except Exception as e:
        print(f"[UDP CLIENT] Произошла ошибка: {e}")
    finally:
        sock.close()


if __name__ == '__main__':
    filename = input("Введите имя файла для скачивания (он должен быть в папке server_files): ")
    if filename:
        run_client(filename)