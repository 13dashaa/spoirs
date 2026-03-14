import socket, time, sys, os
from udp_protocol import *

# Создаем UDP сокет
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server = (sys.argv[1], DEFAULT_PORT)

print(f"Клиент запущен. Подключение к {server}")
print("Команды: DOWNLOAD <имя>, UPLOAD <имя>, ECHO <текст>, TIME, EXIT")

while True:
    try:
        user_input = input("> ").strip()
        if not user_input: continue
        if user_input.upper() == "EXIT": break

        # Отправляем команду
        sock.sendto(user_input.encode(), server)

        # Если это DOWNLOAD, запускаем цикл приема файла
        if user_input.upper().startswith("DOWNLOAD"):
            # 1. Ждем SIZE от сервера
            sock.settimeout(5.0)
            resp, _ = sock.recvfrom(1024)
            if resp.startswith(b"ERROR"):
                print(f"[SERVER]: {resp.decode()}")
                continue

            total_size = int(resp.decode().split()[1])
            print(f"[CLIENT] Прием {total_size} байт...")

            # 2. Прием данных
            start = time.monotonic()
            data = bytearray()
            received = 0

            while received < total_size:
                raw, _ = sock.recvfrom(65536)
                t, _, _, seq, length = struct.unpack(HEADER_FMT, raw[:HEADER_SIZE])

                if t == PACKET_TYPE_FIN: break
                if t == PACKET_TYPE_DATA:
                    data.extend(raw[HEADER_SIZE:HEADER_SIZE + length])
                    received += length
                    # Шлем ACK на каждый пакет (для надежности на клиенте)
                    sock.sendto(pack_pkt(PACKET_TYPE_ACK, seq, 0), server)

            elapsed = time.monotonic() - start
            with open(f"down_{user_input.split()[1]}", "wb") as f:
                f.write(data)
            print(f"[CLIENT] Успешно! Время: {elapsed:.2f} сек. Скорость: {(len(data) / 1024) / elapsed:.2f} КБ/с")
        elif user_input.upper().startswith("UPLOAD"):
            parts = user_input.split()
            filename = parts[1]
            data = open(filename, "rb").read()
            size = len(data)

            # 1. Отправляем команду серверу
            sock.sendto(f"UPLOAD {filename} {size}".encode(), server)

            # 2. Ждем ответ "READY"
            sock.settimeout(5.0)
            resp, _ = sock.recvfrom(1024)

            if resp == b"READY":
                print(f"[CLIENT] Отправляю {size} байт...")
                start = time.monotonic()

                # 3. Отправляем файл чанками прямо здесь (без классов)
                chunks = [data[i:i + 1400] for i in range(0, len(data), 1400)]
                for i, chunk in enumerate(chunks):
                    # Формируем пакет: тип 1 (DATA), seq=i, length=len(chunk)
                    pkt = pack_pkt(PACKET_TYPE_DATA, i, len(chunk), chunk)
                    sock.sendto(pkt, server)
                    # Маленькая пауза, чтобы не "задушить" сервер
                    if i % 100 == 0: time.sleep(0.001)

                    # 4. Шлем FIN
                sock.sendto(pack_pkt(PACKET_TYPE_FIN, 0, 0), server)

                elapsed = time.monotonic() - start
                print(f"[CLIENT] Успешно! Время: {elapsed:.2f} сек. Скорость: {(size / 1024) / elapsed:.2f} КБ/с")
        # Если это ECHO или TIME, просто печатаем ответ
        else:
            sock.settimeout(2.0)
            resp, _ = sock.recvfrom(1024)
            print(f"[SERVER]: {resp.decode()}")

    except socket.timeout:
        print("[CLIENT] Ошибка: Сервер не ответил (таймаут)")
    except Exception as e:
        print(f"[CLIENT] Ошибка: {e}")