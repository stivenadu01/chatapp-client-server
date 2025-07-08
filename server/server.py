import socket
import threading
import queue
import os
import logging
import struct
import time
from datetime import datetime


class ChatServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients = {}
        self.messages_queue = queue.Queue()
        self.running = False
        self.admin_nickname = "SERVER"
        self.setup_loggin()

    def setup_loggin(self):
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] [%(levelname)s] %(message)s",
            handlers=[logging.FileHandler(
                "server.log"), logging.StreamHandler()],
        )

    def broadcast_message(self, sender, message):
        self.messages_queue.put((sender, message))

    def send_text(self, client, msg_type, message):
        try:
            data = message.encode('utf-8')
            header = struct.pack("!II", msg_type, len(data))
            client.sendall(header + data)
        except:
            logging.error(
                f"Error saat mengirim data ke {client.getpeername()}")
            self.remove_client(client)
            self.send_file()

    def send_file(self, client, msg_type, payload):
        try:
            header = struct.pack("!II", msg_type, len(payload))
            client.sendall(header + payload)
        except Exception as e:
            logging.error(
                f"Error saat mengirim file ke {client.getpeername()}: {e}")
            self.remove_client(client)

    def start(self):
        try:
            self.server_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            self.running = True
            logging.info(f"Server Berjalan di {self.host}:{self.port}")
            print("Daftar Perintah:\n/users\n/exit\n")
        except Exception as e:
            logging.info(f"Gagal memulai server: {e}")
            os.exit(1)
            return

        threading.Thread(target=self.dispatch_message, daemon=True).start()
        threading.Thread(target=self.handle_admin_input, daemon=True).start()

        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, addr),
                    daemon=True,
                ).start()
            except Exception as e:
                logging.error(f"Error saat menangani client: {e}")

    def dispatch_message(self):
        while self.running:
            try:
                sender, message = self.messages_queue.get(timeout=1)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                formatted_msg = f"{timestamp}|{sender}|{message}"
                for c in self.clients.keys():
                    # Mengirim pesan ke semua klien
                    self.send_text(c, 1, formatted_msg)
            except queue.Empty:
                continue

    def handle_admin_input(self):
        while self.running:
            try:
                admin_input = input().strip()
                if not admin_input:
                    continue
                if admin_input.startswith('/users'):
                    users = '\n'.join(self.clients.values())
                    print(
                        f"Daftar user online:\n{users if users else "Tidak ada user online"}")
                elif admin_input.startswith("/exit"):
                    self.shutdown()
                    return
                else:
                    self.broadcast_message(self.admin_nickname, admin_input)
            except Exception as e:
                logging.error(f"Error saat menangani input admin: {e}")
                self.shutdown()
                return

    def handle_client(self, client_socket, addr):
        try:
            client_socket.send("NICK".encode('utf-8'))
            nickname = client_socket.recv(1024).decode("utf-8")
            if not nickname:
                raise ValueError("Nickname kosong")
            self.clients[client_socket] = nickname
            logging.info(f"Client {addr} bergabung dengan nama {nickname}")
            join_msg = f"{nickname} Bergabung dalam obrolan"
            self.broadcast_message(self.admin_nickname, join_msg)
            self.update_user_list()

            while self.running:
                try:
                    # Menerima header pesan dari klien
                    header = client_socket.recv(8)
                    if len(header) < 8:
                        logging.error(f"Header dari {nickname, addr} tidak valid")  # noqa: E128
                    msg_type, length = struct.unpack("!II", header)

                    # Membaca data pesan dari klien
                    data = b""
                    while len(data) < length:
                        more = client_socket.recv(length - len(data))
                        if not more:
                            raise ConnectionError("Koneksi client terputus")
                        data += more

                    # Memeriksa tipe pesan
                    if msg_type == 1:  # pesan text
                        message = data.decode("utf-8")
                        self.broadcast_message(nickname, message)
                    elif msg_type == 2:  # private message
                        message = data.decode("utf-8")
                        target, message = message.split(maxsplit=1)
                        self.send_private_message(
                            client_socket, nickname, target, message)
                    elif msg_type == 3:  # file
                        self.broadcast_file(
                            client_socket, nickname, data)
                    if msg_type == 4:  # file private
                        self.send_private_file(
                            client_socket, nickname, data)

                except ConnectionResetError:
                    logging.info(f"Client {nickname} Terputus")
                    break
                except Exception as e:
                    logging.error(f"Error saat menangani {nickname} {addr}: {e}")  # noqa: E128
                    break
        except Exception as e:
            logging.error(f"Error saat menangani {addr}: {e}")
        finally:
            self.remove_client(client_socket)

    def send_private_message(self, sender_socket, sender, target, message):
        for c, n in self.clients.items():
            if n == target:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                formatted_msg = f"{timestamp}|{sender}|{message}"
                self.send_text(c, 2, formatted_msg)
                self.send_text(sender_socket, 2, formatted_msg)
                return
        self.send_text(sender_socket, 5, f"[ERROR] {target} tidak ditemukan")

    def broadcast_file(self, sender_socket, sender, payload):
        file_name, file_data = payload.split(b"|", 1)
        file_name = file_name.decode("utf-8")
        save_dir = "received_files"
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, file_name)
        with open(save_path, "wb") as f:
            f.write(file_data)
        logging.info(
            f"File {file_name} diterima dari {sender} berhasil disimpan")
        payload = sender.encode('utf8') + b"|" + file_name.encode("utf-8") + b"|" + file_data  # noqa: E128
        for c in self.clients.keys():
            self.send_file(c, 3, payload)
        self.send_text(sender_socket, 5,
                       f"[INFO] {file_name} berhasil terkirim")

    def send_private_file(self, sender_socket, sender, payload):
        target, file_name, file_data = payload.split(b"|", 2)
        target = target.decode("utf-8")
        file_name = file_name.decode("utf-8")

        save_dir = "received_files"
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, file_name)
        with open(save_path, "wb") as f:
            f.write(file_data)
        logging.info(
            f"File {file_name} diterima dari {sender} berhasil disimpan")
        payload = sender.encode('utf8') + b"|" + file_name.encode("utf-8") + b"|" + file_data  # noqa: E128
        for c, n in self.clients.items():
            if n == target:
                self.send_file(c, 4, payload)
                self.send_file(sender_socket, 4, payload)
                self.send_text(sender_socket, 5, f"[INFO] {file_name} berhasil terkirim ke {target}")  # noqa: E128)
                return
        self.send_text(sender_socket, 5, f"[ERROR] {target} tidak ditemukan")

    def shutdown(self):
        self.running = False
        for c in self.clients.keys():
            self.send_text(c, 5, "[INFO] Server shutdown")
        time.sleep(5)
        os._exit(1)

    def remove_client(self, client_socket):
        if client_socket in self.clients:
            nickname = self.clients[client_socket]
            client_socket.close()
            del self.clients[client_socket]
            self.broadcast_message(self.admin_nickname,
                                   f"{nickname} Meninggalkan obrolan")
            self.update_user_list()
            return

    def update_user_list(self):
        user_list = ",".join(self.clients.values())
        for c in self.clients.keys():
            self.send_text(c, 5, f"[USER_LIST] {user_list}")


if __name__ == '__main__':
    host = input("Server IP Default (127.0.0.1) : ").strip() or "127.0.0.1"
    port = input("Port Default (65432) : ").strip() or 65432
    server = ChatServer(host=host, port=port)
    server.start()
