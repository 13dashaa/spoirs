import socket, select, os, datetime
from udp_protocol import *

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', DEFAULT_PORT))
sock.setblocking(False)  # ВАЖНО для select

sessions = {}  # {addr: {"type": "upload/download", "data": bytes, "progress": int}}

print(f"[SERVER] Мультиплексированный сервер запущен на {DEFAULT_PORT}")

inputs = [sock]

while True:
    readable, _, _ = select.select(inputs, [], [])

    for s in readable:
        try:
            raw, addr = s.recvfrom(65536)
            t = raw[0]

            # Если это служебный пакет (ACK), логика обработки тут
            if t == PACKET_TYPE_ACK:
                # В реальной задаче здесь нужно обновить прогресс сессии
                continue

            # Если команда
            cmd = raw.decode(errors='ignore').split()
            if not cmd: continue

            if cmd[0] == "ECHO":
                sock.sendto(f"ECHO: {cmd[1]}".encode(), addr)
            elif cmd[0] == "TIME":
                sock.sendto(f"TIME: {datetime.datetime.now()}".encode(), addr)
            elif cmd[0] == "DOWNLOAD":
                # Инициализируем сессию скачивания
                path = os.path.join("server_files", cmd[1])
                if os.path.exists(path):
                    data = open(path, "rb").read()
                    sessions[addr] = {"data": data, "pos": 0}
                    sock.sendto(b"SIZE " + str(len(data)).encode(), addr)

            # --- "ПАРАЛЛЕЛЬНАЯ" ОТПРАВКА ---
            if addr in sessions:
                sess = sessions[addr]
                chunk = sess["data"][sess["pos"]:sess["pos"] + PAYLOAD_SIZE]
                if chunk:
                    seq = sess["pos"] // PAYLOAD_SIZE
                    sock.sendto(pack_pkt(PACKET_TYPE_DATA, seq, len(chunk), chunk), addr)
                    sess["pos"] += len(chunk)
                else:
                    sock.sendto(pack_pkt(PACKET_TYPE_FIN, 0, 0), addr)
                    del sessions[addr]

        except Exception as e:
            print(f"Ошибка: {e}")