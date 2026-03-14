import socket, time, sys
from udp_protocol import *

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server = (sys.argv[1], DEFAULT_PORT)


def download(filename):
    sock.sendto(f"DOWNLOAD {filename}".encode(), server)
    resp, _ = sock.recvfrom(1024)
    size = int(resp.decode().split()[1])

    start = time.monotonic()
    receiver = SlidingWindowReceiver(sock, server, size)
    data = receiver.receive()
    elapsed = time.monotonic() - start

    with open(f"down_{filename}", "wb") as f: f.write(data)
    print(f"Скорость: {(len(data) / 1024) / elapsed:.2f} КБ/с")


download(sys.argv[2])