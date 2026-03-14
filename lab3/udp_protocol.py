import socket, struct


PACKET_TYPE_DATA = 1
PACKET_TYPE_ACK  = 2
PACKET_TYPE_FIN  = 5
HEADER_FMT = "!BBHII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PAYLOAD_SIZE = 1400
DEFAULT_PORT=9091

def pack_pkt(ptype, seq, length, data=b""):
    return struct.pack(HEADER_FMT, ptype, 0, 0, seq, length) + data