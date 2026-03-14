import socket, select, os, datetime
from udp_protocol import *

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', DEFAULT_PORT))
sock.setblocking(False)

FILES_DIR = "server_files"
os.makedirs(FILES_DIR, exist_ok=True)

# sessions хранит состояние: {addr: {"type": "upload", "filename": "...", "data": bytearray(), "size": ...}}
sessions = {}

print(f"[SERVER] Мультиплексированный сервер запущен на {DEFAULT_PORT}")

while True:
    readable, _, _ = select.select([sock], [], [])

    for s in readable:
        try:
            raw, addr = s.recvfrom(65536)
            t = raw[0]  # Тип пакета

            # --- Обработка команд (если это не данные) ---
            if t not in (PACKET_TYPE_DATA, PACKET_TYPE_FIN, PACKET_TYPE_ACK):
                cmd_str = raw.decode(errors='ignore').strip()
                cmd_parts = cmd_str.split(None, 2)
                if not cmd_parts: continue
                cmd = cmd_parts[0].upper()

                print(f"[SERVER] Команда от {addr}: {cmd}")

                if cmd == "ECHO":
                    sock.sendto(f"ECHO: {cmd_parts[1]}".encode(), addr)
                elif cmd == "TIME":
                    sock.sendto(f"TIME: {datetime.datetime.now()}".encode(), addr)
                elif cmd == "UPLOAD":
                    filename, size = cmd_parts[1], int(cmd_parts[2])
                    sessions[addr] = {"type": "upload", "filename": filename, "data": bytearray(), "size": size}
                    sock.sendto(b"READY", addr)

            # --- Обработка данных (для UPLOAD) ---
            elif addr in sessions and sessions[addr]["type"] == "upload":
                if t == PACKET_TYPE_DATA:
                    seq, length = struct.unpack("!II", raw[4:12])  # seq, length
                    sessions[addr]["data"].extend(raw[HEADER_SIZE:HEADER_SIZE + length])
                    sock.sendto(pack_pkt(PACKET_TYPE_ACK, seq, 0), addr)

                    if len(sessions[addr]["data"]) >= sessions[addr]["size"]:
                        with open(os.path.join(FILES_DIR, sessions[addr]["filename"]), "wb") as f:
                            f.write(sessions[addr]["data"])
                        print(f"[SERVER] UPLOAD {sessions[addr]['filename']} завершен!")
                        del sessions[addr]

        except Exception as e:
            print(f"[SERVER] Ошибка: {e}")