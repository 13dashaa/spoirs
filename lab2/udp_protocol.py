import socket, struct, time

PACKET_TYPE_DATA = 1
PACKET_TYPE_ACK = 2
PACKET_TYPE_FIN = 5
HEADER_FMT = "!BBHII"  # Type, Flags, Window, Seq, Length
HEADER_SIZE = struct.calcsize(HEADER_FMT)
DEFAULT_PORT = 9091
PAYLOAD_SIZE = 32000  # Оптимально для Python-UDP


class SlidingWindowSender:
    def __init__(self, sock, addr):
        self.sock, self.addr = sock, addr
        self.sock.setblocking(False)

    def send(self, data):
        chunks = [data[i:i + PAYLOAD_SIZE] for i in range(0, len(data), PAYLOAD_SIZE)]
        n = len(chunks)
        base = 0
        next_seq = 0
        window = 100
        start = time.monotonic()

        while base < n:
            while next_seq < base + window and next_seq < n:
                pkt = struct.pack(HEADER_FMT, PACKET_TYPE_DATA, 0, 0, next_seq, len(chunks[next_seq])) + chunks[
                    next_seq]
                self.sock.sendto(pkt, self.addr)
                next_seq += 1
            try:
                raw, _ = self.sock.recvfrom(64)
                ack_seq = struct.unpack(HEADER_FMT, raw[:HEADER_SIZE])[3]
                if ack_seq >= base: base = ack_seq + 1
            except:
                time.sleep(0.001)

        # FIN пакет
        for _ in range(5): self.sock.sendto(struct.pack(HEADER_FMT, PACKET_TYPE_FIN, 0, 0, 0, 0), self.addr)
        return len(data), time.monotonic() - start


class SlidingWindowReceiver:
    def __init__(self, sock, addr, total_bytes):
        self.sock, self.addr = sock, addr
        self.total = total_bytes

    def receive(self):
        buf = {}
        expected = 0
        received_bytes = 0
        data = bytearray()
        while received_bytes < self.total:
            try:
                raw, addr = self.sock.recvfrom(65536)
                t, _, _, seq, length = struct.unpack(HEADER_FMT, raw[:HEADER_SIZE])
                if t == PACKET_TYPE_FIN: break
                if seq >= expected:
                    buf[seq] = raw[HEADER_SIZE:HEADER_SIZE + length]
                    while expected in buf:
                        data.extend(buf.pop(expected))
                        received_bytes += len(data)  # Упрощенно
                        expected += 1
                    self.sock.sendto(struct.pack(HEADER_FMT, PACKET_TYPE_ACK, 0, 0, expected - 1, 0), addr)
            except:
                continue
        return bytes(data)