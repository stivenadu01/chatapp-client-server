import socket
import threading
import tkinter as tk
from tkinter import filedialog, simpledialog, scrolledtext, messagebox
import struct
import os
import json
from datetime import datetime
import random


class ChatClient:
    def __init__(self):
        self.master = tk.Tk()
        self.master.title("Chat Client")
        self.master.minsize(720, 480)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.nickname = self.load_or_ask_nickname()
        self.in_pm_mode = False
        self.pm_target = ''
        self.online_users = []
        self.file_masuk = {}
        self.file_keluar = {}
        self.build_gui()
        self.connect()
        self.master.mainloop()

    def build_gui(self):
        # Frame utama
        self.master.option_add("*Font", ("Roboto", 12))
        main_frame = tk.Frame(self.master)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.master.columnconfigure(0, weight=1)  # kolom fleksibel
        self.master.rowconfigure(0, weight=1)  # row fleksibel

        # Konfigurasi kolom dan baris dalam main_frame
        main_frame.columnconfigure(0, weight=1)  # Kolom 0 fleksibel
        main_frame.columnconfigure(1, weight=0)  # Kolom 1 tetap
        main_frame.rowconfigure(0, weight=1)     # Baris atas (chat & listbox)
        main_frame.rowconfigure(1, weight=0)     # Baris bawah (entry & tombol)

        # Chat Area (row 0, column 0)
        self.chat_area = scrolledtext.ScrolledText(
            main_frame, wrap=tk.WORD, state="disabled"
        )
        self.chat_area.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # tag konfigurasi chat area
        self.chat_area.tag_configure(
            "pm", foreground="#a64ca6")  # ungu elegan untuk PM
        self.chat_area.tag_configure("left", justify="left")
        self.chat_area.tag_configure("right", justify="right")
        self.chat_area.tag_configure("center", justify="center")
        self.chat_area.tag_configure(
            "timestamp", font=("Roboto", 9), foreground="#696969")
        self.chat_area.tag_configure("sender", foreground="#095C00")

        # User Listbox (row 0, column 1)
        self.user_listbox = tk.Listbox(main_frame)
        self.user_listbox.grid(
            row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.user_listbox.bind("<Double-Button-1>", self.select_user_for_pm)

        # Entry message (row 1, column 0)
        self.entry_msg = tk.Entry(main_frame)
        self.entry_msg.grid(row=1, column=0, padx=10,
                            pady=(0, 10), sticky="ew", ipady=5)
        self.entry_msg.bind("<Return>", self.send_message)
        self.entry_msg.focus()

        # Tombol frame (row 1, column 1)
        self.button_frame = tk.Frame(main_frame)
        self.button_frame.grid(row=1, column=1, padx=(
            0, 10), pady=(0, 10), sticky="ew")

        # Tombol
        tk.Button(
            self.button_frame, text="Kirim", command=self.send_message).pack(side=tk.LEFT)
        tk.Button(
            self.button_frame, text="File", command=self.send_file).pack(side=tk.LEFT)
        tk.Button(self.button_frame, text="Keluar PM", command=self.exit_pm).pack(
            side=tk.LEFT
        )

    def connect(self):
        try:
            self.host = simpledialog.askstring(
                "Connect", "Masukan ip server", parent=self.master)
            self.port = simpledialog.askinteger(
                "Connect", "Masukan port server", parent=self.master)

            self.socket.connect((self.host, self.port))
            res = self.socket.recv(1024).decode('utf-8')
            if res == "NICK":
                self.socket.send(self.nickname.encode('utf-8'))

        except Exception as e:
            messagebox.showerror("Error", f"Gagal terhubung ke server: {e}")
            self.master.destroy()
            return

        threading.Thread(target=self.receive_messages, daemon=True).start()

    def receive_messages(self):

        while True:
            try:
                header = self.socket.recv(8)
                if len(header) < 8:
                    messagebox.showerror(
                        "Error", "Error saat menerima header.")
                    break
                msg_type, msg_len = struct.unpack("!II", header)

                # terima data
                data = b''
                while len(data) < msg_len:
                    more = self.socket.recv(msg_len - len(data))
                    if not more:
                        messagebox.showerror(
                            "Error", "Error saat menerima data.")
                        break
                    data += more

                if msg_type in [1, 2]:
                    message = data.decode('utf-8')
                    self.show_message(message, msg_type)

                if msg_type in [3, 4]:  # file broadcast
                    sender, file_name, file_data = data.split(b'|', 2)
                    sender = sender.decode('utf-8')
                    file_name = file_name.decode('utf-8')
                    file_size = len(file_data)
                    # simpan sementara di ram
                    self.file_masuk[file_name] = {
                        "data": file_data, "is_new": True}
                    # tampilkan di chat
                    self.show_file(sender, file_name, file_size, msg_type)

                if msg_type == 5:  # control message
                    data = data.decode('utf-8')
                    if data.startswith("[USER_LIST]"):
                        user_list = data.replace(
                            "[USER_LIST]", "").strip().split(",")
                        self.update_user_list(user_list)
                    if data.startswith("[ERROR]"):
                        messagebox.showerror(
                            "Error", data.replace("[ERROR]", ""))
                    if data.startswith("[INFO]"):
                        messagebox.showinfo(
                            "Info", data.replace("[INFO]", ""))
                        if data.replace("[INFO]", "").strip() == "Server shutdown":
                            self.master.destroy()
                            self.socket.close()
            except ConnectionResetError:
                messagebox.showerror(
                    "Error", "Koneksi ke server terputus.")
                self.master.destroy()
                self.socket.close()
                break
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Error saat menerima pesan: {e}")
                self.master.destroy()
                self.socket.close()

    def send_message(self, event=None):
        message = self.entry_msg.get().strip()
        if not message:
            return

        if self.in_pm_mode:
            msg_type = 2
            message = f"{self.pm_target} {message}"
        else:
            msg_type = 1

        data = message.encode('utf-8')
        msg_len = len(data)
        try:
            header = struct.pack("!II", msg_type, msg_len)
            self.socket.send(header + data)
            self.entry_msg.delete(0, tk.END)
        except:
            messagebox.showerror("Error", "Error saat mengirim pesan.")

    def send_file(self):
        path = filedialog.askopenfilename()
        if not path:
            return

        try:
            file_name = os.path.basename(path)
            oke = messagebox.askyesno(
                "Konfirmasi", f"Apakah Anda yakin ingin mengirim file {file_name}?")
            if not oke:
                return

            with open(path, "rb") as f:
                file_data = f.read()
            if self.in_pm_mode:
                msg_type = 4
                payload = self.pm_target.encode(
                    'utf-8') + b'|' + file_name.encode('utf-8') + b'|' + file_data
            else:
                payload = file_name.encode('utf-8') + b'|' + file_data
                msg_type = 3

            # header: msg_type, len
            header = struct.pack("!II", msg_type, len(payload))
            self.socket.send(header + payload)
            self.file_keluar[file_name] = path

        except Exception as e:
            messagebox.showerror("Error", f"Error saat mengirim file: {e}")

    def show_file(self, sender, file_name, file_size, msg_type):
        self.chat_area.configure(state="normal")
        # hitung ukuran file dalam KB atau MB
        if file_size < 1024:
            size_str = f"{file_size} bytes"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.2f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.2f} MB"

        # tentukan tag untuk sender
        if sender == self.nickname:
            tag_sender = "right"
        else:
            tag_sender = "left"

        # tampilkan head
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.chat_area.insert(
            tk.END, f"{timestamp}", ("timestamp", tag_sender))
        format_sender = sender
        if msg_type == 4:
            format_sender = f"{sender} 🔏 [PM]"
        self.chat_area.insert(
            tk.END, f"\t{format_sender}\n" if sender != self.nickname else "\n", ("sender", tag_sender))

        # tampilkan text di chat area
        self.chat_area.insert(
            tk.END, f"{file_name} ({size_str})\n", tag_sender)

        tag_name = file_name+str(random.randint(1, 1000000))
        # tambahkan tag seperti hyperlink
        self.chat_area.tag_add(
            tag_name, "end-2l linestart", "end-2l lineend")
        warna = "blue" if self.file_masuk[file_name]["is_new"] else "black"
        warna = "black" if sender == self.nickname else warna
        self.chat_area.tag_configure(
            tag_name, foreground=warna, underline=True)

        # Tambahkan binding interaktif
        self.chat_area.tag_bind(
            tag_name, "<Enter>", lambda e: self.chat_area.configure(cursor="hand2"))
        self.chat_area.tag_bind(tag_name, "<Leave>",
                                lambda e: self.chat_area.configure(cursor=""))
        if sender == self.nickname:
            self.chat_area.tag_bind(
                tag_name, "<Button-1>", lambda e, f=file_name: self.open_file_from_memory(f))
        else:
            self.chat_area.tag_bind(
                tag_name, "<Button-1>", lambda e, f=file_name, t=tag_name: self.handle_click_file(f, t))

        self.chat_area.configure(state="disabled")
        self.chat_area.see(tk.END)

    def open_file_from_memory(self, file_name):
        path = self.file_keluar[file_name]
        if not os.path.exists(path):
            messagebox.showerror("Error", "File tidak ditemukan.")
            return
        os.startfile(path)

    def handle_click_file(self, file_name, tag_name):
        try:
            file_data = self.file_masuk[file_name]["data"]
            if not file_data:
                messagebox.showerror("Error", "File tidak ditemukan.")
                return
            save_dir = "downloads"
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, file_name)
            if not self.file_masuk[file_name]["is_new"]:
                os.startfile(save_path)
                return
            with open(save_path, "wb") as f:
                f.write(file_data)
            self.file_masuk[file_name]["is_new"] = False
            self.chat_area.after(1000, lambda: self.chat_area.tag_config(
                tag_name, foreground="purple"))
            # untuk windows
            os.startfile(save_path)
        except Exception as e:
            messagebox.showerror("Error", f"Error saat download file: {e}")
            return

    def select_user_for_pm(self, event):
        select = self.user_listbox.curselection()
        if select:
            user = self.user_listbox.get(select[0])
            self.in_pm_mode = True
            self.pm_target = user
            self.show_message(f"🔏 Anda memulai PM dengan {user}")

    def load_or_ask_nickname(self):
        config_path = "config.json"

        # Coba baca dari file config
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    nickname = config.get("nickname", "")
                    if nickname.strip():
                        return nickname
            except Exception as e:
                print(f"[ERROR] Gagal membaca config: {e}")

        # Kalau tidak ada atau nickname kosong → minta input
        while True:
            nickname = simpledialog.askstring(
                "Nickname", "Masukkan nickname Anda:")
            if nickname:
                try:
                    with open(config_path, "w") as f:
                        json.dump({"nickname": nickname}, f)
                except Exception as e:
                    print(f"[ERROR] Gagal menyimpan config: {e}")
                return nickname
            else:
                messagebox.showerror("Error", "Nickname tidak boleh kosong.")

    def show_message(self, message, msg_type=0):
        self.chat_area.configure(state="normal")

        if msg_type == 0:  # jika bukan dari server
            self.chat_area.insert(tk.END, message + "\n", "center")
            self.chat_area.configure(state="disabled")
            return

        # pisahkan timestamp , sender dan content
        try:
            timestamp, sender, content = message.split("|", 2)
        except ValueError:
            # Kalau format salah, tampilkan seadanya
            self.chat_area.insert(tk.END, content + "\n", "left")
            self.chat_area.configure(state="disabled")
            return

        if sender == self.nickname:
            tag_sender = 'right'
        elif sender == "SERVER":
            tag_sender = 'center'
        else:
            tag_sender = 'left'

        tag_pm = None
        format_sender = sender
        if msg_type == 2:  # jika pm
            tag_pm = "pm"
            format_sender += " 🔏[PM]"

        self.chat_area.insert(tk.END, timestamp or '',
                              (tag_sender, "timestamp"))
        self.chat_area.insert(
            tk.END, f"\t{format_sender}" if tag_sender == 'left' else '', (tag_sender, "sender"))
        self.chat_area.insert(tk.END,  "\n" + content +
                              "\n", (tag_sender, tag_pm))
        self.chat_area.configure(state="disabled")
        self.chat_area.yview(tk.END)

    def update_user_list(self, user):
        self.user_listbox.delete(0, tk.END)
        for u in user:
            if u != self.nickname:
                self.user_listbox.insert(tk.END, u)

    def exit_pm(self):
        self.in_pm_mode = False
        self.pm_target = None
        self.show_message("🔐 Anda keluar dari PM.")


if __name__ == '__main__':
    client = ChatClient()
