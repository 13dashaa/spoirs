import socket, select, os, datetime, struct
from udp_protocol import *

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', DEFAULT_PORT))
sock.setblocking(False)

FILES_DIR = "server_files"
os.makedirs(FILES_DIR, exist_ok=True)

# sessions хранит состояние всех активных передач
# {addr: {"type": "upload"|"download", "filename": "...", "data": ..., "pos": ..., "size": ...}}
sessions = {}

print(f"[SERVER] Мультиплексированный сервер запущен на {DEFAULT_PORT}")

while True:
    readable, _, _ = select.select([sock], [], [])
    for s in readable:
        try:
            raw, addr = s.recvfrom(65536)
            t = raw[0]  # Тип пакета

            # 1. ОБРАБОТКА КОМАНД (текстовые пакеты)
            if t not in (PACKET_TYPE_DATA, PACKET_TYPE_FIN, PACKET_TYPE_ACK):
                cmd_str = raw.decode(errors='ignore').strip()
                parts = cmd_str.split()
                if not parts: continue

                cmd = parts[0].upper()
                print(f"[SERVER] Команда от {addr}: {cmd}")

                if cmd == "ECHO":
                    sock.sendto(f"ECHO: {' '.join(parts[1:])}".encode(), addr)

                elif cmd == "TIME":
                    sock.sendto(f"TIME: {datetime.datetime.now()}".encode(), addr)

                elif cmd == "UPLOAD":
                    filename, size = parts[1], int(parts[2])
                    sessions[addr] = {"type": "upload", "filename": filename, "data": bytearray(), "size": size}
                    sock.sendto(b"READY", addr)

                elif cmd == "DOWNLOAD":
                    path = os.path.join(FILES_DIR, parts[1])
                    if os.path.exists(path):
                        data = open(path, "rb").read()
                        sock.sendto(f"SIZE {len(data)}".encode(), addr)
                        sessions[addr] = {"type": "download", "data": data, "pos": 0, "size": len(data)}
                    else:
                        sock.sendto(b"ERROR: FILE NOT FOUND", addr)

            # 2. ОБРАБОТКА ПОТОКА ДАННЫХ
            elif addr in sessions:
                sess = sessions[addr]

                if sess["type"] == "upload" and t == PACKET_TYPE_DATA:
                    # Принимаем UPLOAD по частям
                    _, seq, length = struct.unpack("!BII", raw[:9])
                    sess["data"].extend(raw[HEADER_SIZE:HEADER_SIZE + length])
                    sock.sendto(pack_pkt(PACKET_TYPE_ACK, seq, 0), addr)

                    if len(sess["data"]) >= sess["size"]:
                        with open(os.path.join(FILES_DIR, sess["filename"]), "wb") as f: f.write(sess["data"])
                        print(f"[SERVER] UPLOAD {sess['filename']} завершен.")
                        del sessions[addr]

                elif sess["type"] == "download":
                    # Отправляем DOWNLOAD по частям
                    if t == PACKET_TYPE_ACK:
                        # Получили ACK, можно слать следующий кусок
                        chunk = sess["data"][sess["pos"]:sess["pos"] + PAYLOAD_SIZE]
                        if chunk:
                            sock.sendto(pack_pkt(PACKET_TYPE_DATA, sess["pos"] // PAYLOAD_SIZE, len(chunk), chunk),
                                        addr)
                            sess["pos"] += len(chunk)
                        else:
                            sock.sendto(pack_pkt(PACKET_TYPE_FIN, 0, 0), addr)
                            del sessions[addr]
                            print("[SERVER] DOWNLOAD завершен.")

        except Exception as e:
            print(f"[SERVER] Ошибка: {e}")