import socket
import struct
import time

PACKET_TYPE_DATA = 0x01
PACKET_TYPE_ACK = 0x02
PACKET_TYPE_CMD = 0x03
PACKET_TYPE_CMDACK = 0x04
PACKET_TYPE_FIN = 0x05

HEADER_FORMAT = "!BBHII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 12 байт
DEFAULT_PORT = 9091

# =========================================================================
# МАГИЯ ПРОИЗВОДИТЕЛЬНОСТИ
# 32000 байт - оптимальный размер. Он сильно больше MTU (1500), что
# заставляет ядро ОС выполнять фрагментацию IP на уровне ядра (очень быстро),
# и минимизирует количество тормозящих вызовов sendto() в Python.
# =========================================================================
MAX_PAYLOAD_SIZE = 32000
WINDOW_SIZE = 200  # Окно: 200 пакетов * 32 КБ = ~6.4 МБ в полете
TIMEOUT = 0.2  # Таймаут повторной отправки
ACK_INTERVAL = 10  # Шлем ACK каждый 10-й пакет (разгрузка сети)


# =========================================================================

def pack_header(ptype, seq, length, flags=0, window=WINDOW_SIZE):
    return struct.pack(HEADER_FORMAT, ptype, flags, window, seq, length)


def unpack_header(data):
    ptype, flags, window, seq, length = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    return ptype, flags, window, seq, length, data[HEADER_SIZE:]


class SlidingWindowSender:
    def __init__(self, sock, addr, window_size=WINDOW_SIZE, timeout=TIMEOUT):
        self._sock = sock
        self._addr = addr
        self._window = window_size
        self._timeout = timeout

    def send(self, data, ptype=PACKET_TYPE_DATA):
        chunks = [data[i:i + MAX_PAYLOAD_SIZE] for i in range(0, max(len(data), 1), MAX_PAYLOAD_SIZE)]
        n = len(chunks)
        if n == 0: return 0, 0.0

        print(f"[PROTO] Отправка {len(data)} байт ({n} пакетов), буфер={MAX_PAYLOAD_SIZE}B")

        original_timeout = self._sock.gettimeout()
        # Переводим сокет в неблокирующий режим для максимальной скорости!
        self._sock.setblocking(False)

        local_port = self._sock.getsockname()[1]
        start = time.monotonic()

        base = 0
        next_seq = 0
        last_ack_time = time.monotonic()

        # Предварительно пакуем заголовки для ускорения
        packets = [pack_header(ptype, i, len(chunks[i]), window=local_port) + chunks[i] for i in range(n)]

        while base < n:
            # 1. Заполняем окно на максимальной скорости
            while next_seq < base + self._window and next_seq < n:
                try:
                    self._sock.sendto(packets[next_seq], self._addr)
                    next_seq += 1
                except BlockingIOError:
                    # Буфер ОС переполнен, прерываем цикл отправки, идем читать ACK
                    break
                except OSError as e:
                    # Игнорируем временные ошибки сети
                    if e.errno != 111: pass

            # 2. Неблокирующее чтение ACK
            try:
                while True:
                    raw, addr = self._sock.recvfrom(64)
                    if addr[0] != self._addr[0]: continue

                    ptype_ack, _, _, seq, _, _ = unpack_header(raw)
                    if ptype_ack == PACKET_TYPE_ACK:
                        if seq >= base:
                            base = seq + 1  # Кумулятивный ACK, сдвигаем базу
                            last_ack_time = time.monotonic()
            except BlockingIOError:
                pass  # Нет новых ACK в буфере

            # 3. Обработка таймаута (потеря пакета)
            if time.monotonic() - last_ack_time > self._timeout:
                # Переотправляем пакеты начиная с base
                next_seq = base
                last_ack_time = time.monotonic()
                time.sleep(0.005)  # Небольшая пауза, чтобы сеть "продышалась"

        # 4. Сообщаем о завершении (FIN)
        self._sock.setblocking(True)
        self._sock.settimeout(0.1)
        for _ in range(10):  # Отправляем несколько раз для надежности
            self._sock.sendto(pack_header(PACKET_TYPE_FIN, n, 0), self._addr)
            time.sleep(0.01)

        self._sock.settimeout(original_timeout)
        elapsed = time.monotonic() - start or 0.001
        print(f"[PROTO] Успешно: {len(data) / 1024 / elapsed:.1f} КБ/с")
        return len(data), elapsed


class SlidingWindowReceiver:
    def __init__(self, sock, addr, total_bytes, ptype=PACKET_TYPE_DATA, timeout=30):
        self._sock = sock
        self._addr = addr
        self._total = total_bytes
        self._ptype = ptype
        self._timeout = timeout

    def receive(self):
        try:
            # Максимально увеличиваем буфер приема в ОС
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 64 * 1024 * 1024)
        except OSError:
            pass

        original_timeout = self._sock.gettimeout()
        self._sock.settimeout(1.0)

        data_chunks = {}  # Буфер для сборки файла
        expected = 0
        received_bytes = 0

        last_packet_time = time.monotonic()
        sender_addr = None
        last_report = time.monotonic()

        print(f"[PROTO] Ожидаю {self._total} байт (chunk size ~{MAX_PAYLOAD_SIZE})")

        while received_bytes < self._total:
            try:
                raw, addr = self._sock.recvfrom(65536)
                last_packet_time = time.monotonic()
                if not sender_addr: sender_addr = addr
            except socket.timeout:
                if time.monotonic() - last_packet_time > self._timeout:
                    self._sock.settimeout(original_timeout)
                    raise TimeoutError("Обрыв связи")
                continue

            if sender_addr and addr[0] != sender_addr[0]: continue

            ptype, _, ack_port, seq, length, payload = unpack_header(raw)

            if ptype == PACKET_TYPE_FIN:
                break
            if ptype != self._ptype:
                continue

            ack_dest = (addr[0], ack_port)

            if seq == expected:
                data_chunks[seq] = payload[:length]
                received_bytes += length
                expected += 1

                # Подтягиваем буферизованные пакеты
                while expected in data_chunks:
                    expected += 1

                # Шлем ACK периодически или если это последний нужный пакет
                if expected % ACK_INTERVAL == 0 or received_bytes >= self._total:
                    try:
                        self._sock.sendto(pack_header(PACKET_TYPE_ACK, expected - 1, 0), ack_dest)
                    except OSError:
                        pass

            elif seq > expected:
                # Пакет из будущего (потеряли предыдущие). Сохраняем.
                if seq not in data_chunks:
                    data_chunks[seq] = payload[:length]
                    received_bytes += length
                # Сразу шлем DUP ACK, чтобы спровоцировать Fast Retransmit у отправителя
                try:
                    self._sock.sendto(pack_header(PACKET_TYPE_ACK, expected - 1, 0), ack_dest)
                except OSError:
                    pass

            elif seq < expected:
                # Пришел старый пакет. Напоминаем наш expected
                try:
                    self._sock.sendto(pack_header(PACKET_TYPE_ACK, expected - 1, 0), ack_dest)
                except OSError:
                    pass

            # Отчет в консоль (редко, чтобы не тормозить процесс)
            now = time.monotonic()
            if now - last_report > 1.0:
                print(f"[PROTO] Прогресс: {(received_bytes / self._total) * 100:.1f}%")
                last_report = now

        self._sock.settimeout(original_timeout)

        # Склеиваем байты в правильном порядке
        result = bytearray()
        for i in range(expected):
            if i in data_chunks:
                result.extend(data_chunks[i])

        return bytes(result)