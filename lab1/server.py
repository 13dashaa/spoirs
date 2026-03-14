import socket
import datetime

HOST = '0.0.0.0'
PORT = 9090


def handle_client_connection(client_socket, address):
    print(f"[INFO] Принято соединение от {address}")

    request_buffer = b""

    try:
        while True:
            chunk = client_socket.recv(1024)
            if not chunk:
                print(f"[INFO] Клиент {address} разорвал соединение.")
                break

            request_buffer += chunk

            while b'\n' in request_buffer:
                command_line, request_buffer = request_buffer.split(b'\n', 1)

                command_str = command_line.decode('utf-8').strip()

                if not command_str:
                    continue

                print(f"[COMMAND] Получена команда от {address}: {command_str}")

                parts = command_str.split(' ', 1)
                command = parts[0].upper()
                args = parts[1] if len(parts) > 1 else ""

                if command == 'ECHO':
                    response = args + '\r\n'
                elif command == 'TIME':
                    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    response = now + '\r\n'
                elif command in ('CLOSE', 'EXIT', 'QUIT'):
                    response = 'Goodbye!\r\n'
                    client_socket.sendall(response.encode('utf-8'))
                    return
                else:
                    response = 'ERROR: Unknown command\r\n'

                client_socket.sendall(response.encode('utf-8'))

    except ConnectionResetError:
        print(f"[ERROR] Соединение с {address} было принудительно разорвано.")
    except Exception as e:
        print(f"[ERROR] Произошла ошибка при работе с {address}: {e}")
    finally:
        print(f"[INFO] Закрываем соединение с {address}.")
        client_socket.close()


def run_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_socket.bind((HOST, PORT))

    server_socket.listen(5)
    print(f"[INFO] Сервер запущен и слушает на {HOST}:{PORT}")

    try:
        while True:
            client_sock, address = server_socket.accept()
            handle_client_connection(client_sock, address)
    except KeyboardInterrupt:
        print("\n[INFO] Сервер останавливается по команде пользователя.")
    finally:
        server_socket.close()
        print("[INFO] Сервер успешно остановлен.")


if __name__ == '__main__':
    run_server()