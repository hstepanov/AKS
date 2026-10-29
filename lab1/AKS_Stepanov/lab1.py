import json
import os
import re
import string
import tkinter as tk
from tkinter import messagebox, ttk

DB_FILE = "users_db.json"
DEFAULT_USERS = ["Stepanov_1", "Stepanov_2", "Stepanov_3", "Stepanov_4", "Stepanov_5"]


def init_db():
    """Створення та ініціалізація бази даних JSON з 5 користувачами.
    Stepanov_1 робимо адміністратором (is_admin = True), решта — звичайні користувачі.
    """
    if not os.path.exists(DB_FILE):
        db_data = {}
        for i, username in enumerate(DEFAULT_USERS):
            db_data[username] = {
                "password": str(username),
                "is_complex": True, 
                "is_admin": (i == 0)  # адмін - перший користувач з DEFAULT_USERS
            }
        save_db(db_data)


def load_db() -> dict:
    init_db()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        messagebox.showerror(f"Не вдалося завантажити БД: {e}")
        return {}


def save_db(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def validate_password(password: str, is_complex: bool) -> tuple[bool, str]:
    if is_complex:
        if len(password) < 8:
            return False, "Складний пароль повинен містити не менше 8 символів!"

        sets_count = 0
        if re.search(r"[a-z]", password):
            sets_count += 1
        if re.search(r"[A-Z]", password):
            sets_count += 1
        if re.search(r"\d", password):
            sets_count += 1
        if re.search(f"[{re.escape(string.punctuation)}]", password):
            sets_count += 1

        if sets_count < 3:
            return False, (
                "Складний пароль повинен містити символи мінімум з 3-х наборів:\n"
                "1) Малі літери (a-z)\n"
                "2) Великі літери (A-Z)\n"
                "3) Цифри (0-9)\n"
                "4) Спецсимволи (!@#$%^&*...)"
            )
    return True, ""


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        # Заголовок головного вікна
        self.title("AdmKS_Stepanov")
        self.geometry("480x380")
        self.resizable(False, False)

        self.configure(bg="#ececec")
        self.update_idletasks()

        self.current_user = None
        self.db = load_db()

        self.create_menu()
        self.build_auth_ui()

    # Про автора
    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        author_menu = tk.Menu(menubar, tearoff=0)
        author_menu.add_command(label="Про автора", command=self.show_author_info)
        menubar.add_cascade(label="Інформація", menu=author_menu)

    def show_author_info(self):
        messagebox.showinfo("Про автора", "KSDM-51, Mykola Stepanov")

    # Перемикання інтерфейсів
    def clear_frame(self):
        for widget in self.winfo_children():
            if not isinstance(widget, tk.Menu):
                widget.destroy()

    # інтерфейс автентифікації користувача
    def build_auth_ui(self):
        self.clear_frame()

        frame = ttk.Frame(self, padding="20")
        frame.pack(expand=True, fill="both")

        ttk.Label(frame, text="Автентифікація", font=("Arial", 14, "bold")).pack(pady=10)

        ttk.Label(frame, text="Ім'я користувача:").pack(anchor="w", pady=(5, 0))
        username_entry = ttk.Entry(frame, width=35)
        username_entry.pack(pady=5)

        ttk.Label(frame, text="Пароль:").pack(anchor="w", pady=(5, 0))
        password_entry = ttk.Entry(frame, show="*", width=35)
        password_entry.pack(pady=5)

        def login():
            user = username_entry.get().strip()
            pwd = password_entry.get()

            if user not in self.db:
                messagebox.showerror("Error", "Користувача не знайдено!")
                return

            if self.db[user]["password"] == pwd:
                self.current_user = user
                self.build_dashboard_ui()
            else:
                messagebox.showerror("Error", "Невірний пароль")

        ttk.Button(frame, text="Залогінитись", command=login).pack(pady=15)

    # Панель управління після успішного входу
    def build_dashboard_ui(self):
        self.clear_frame()

        frame = ttk.Frame(self, padding="20")
        frame.pack(expand=True, fill="both")

        # Перевірка, чи є поточний юзер адміном
        is_admin = self.db[self.current_user].get("is_admin", False)

        ttk.Label(
            frame, 
            text=f"Вітаю {self.current_user}!\n", 
            font=("Arial", 12, "bold"), 
            foreground="green",
            justify="center"
        ).pack(pady=10)

        # Кнопка додавання доступна тільки адміністраторам
        if is_admin:
            ttk.Button(
                frame, 
                text="Додати нового користувача", 
                command=self.open_add_user_dialog, 
                width=30
            ).pack(pady=5)

        ttk.Button(
            frame, 
            text="Змінити пароль", 
            command=self.open_change_password_dialog, 
            width=30
        ).pack(pady=5)

        ttk.Button(
            frame, 
            text="Вийти з акаунту", 
            command=self.build_auth_ui, 
            width=30
        ).pack(pady=15)

    # Додати нового користувача з можливістю вказати права
    def open_add_user_dialog(self):
        if not self.db[self.current_user].get("is_admin", False):
            messagebox.showerror("Цю дію може виконувати лише адміністратор")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Додати користувача")
        dialog.geometry("380x320")
        dialog.grab_set()

        ttk.Label(dialog, text="Логін").pack(anchor="w", padx=20, pady=(15, 0))
        user_entry = ttk.Entry(dialog, width=30)
        user_entry.pack(padx=20, pady=5)

        ttk.Label(dialog, text="Пароль").pack(anchor="w", padx=20, pady=(5, 0))
        pwd_entry = ttk.Entry(dialog, show="*", width=30)
        pwd_entry.pack(padx=20, pady=5)

        is_complex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog, 
            text="Необхідний складний пароль", 
            variable=is_complex_var
        ).pack(anchor="w", padx=20, pady=5)

        is_admin_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog, 
            text="Адміністратор", 
            variable=is_admin_var
        ).pack(anchor="w", padx=20, pady=5)

        def save_user():
            new_user = user_entry.get().strip()
            new_pwd = pwd_entry.get()
            is_complex = is_complex_var.get()
            is_admin = is_admin_var.get()

            if not new_user:
                messagebox.showerror("Error", "Ім'я користувача не може бути порожнім", parent=dialog)
                return

            if new_user in self.db:
                messagebox.showerror("Error", "Користувач з таким іменем вже існує", parent=dialog)
                return

            valid, msg = validate_password(new_pwd, is_complex)
            if not valid:
                messagebox.showerror("Error", f"Помилка перевірки пароля: {msg}", parent=dialog)
                return

            self.db[new_user] = {
                "password": new_pwd,
                "is_complex": is_complex,
                "is_admin": is_admin
            }
            save_db(self.db)
            messagebox.showinfo("Info", f"Користувач {new_user} доданий", parent=dialog)
            dialog.destroy()

        ttk.Button(dialog, text="Створити", command=save_user).pack(pady=15)

    # Зміна пароля для поточного залогіненого користувача
    def open_change_password_dialog(self):
        is_admin = self.db[self.current_user].get("is_admin", False)

        dialog = tk.Toplevel(self)
        dialog.title("Зміна пароля")
        dialog.geometry("380x300")
        dialog.grab_set()

        if is_admin:
            ttk.Label(dialog, text="Оберіть користувача:").pack(anchor="w", padx=20, pady=(15, 0))
            user_select = ttk.Combobox(dialog, values=list(self.db.keys()), state="readonly", width=28)
            user_select.set(self.current_user)
            user_select.pack(padx=20, pady=5)
        else:
            ttk.Label(dialog, text=f"Користувач: {self.current_user}", font=("Arial", 11, "bold")).pack(anchor="w", padx=20, pady=(15, 0))


        ttk.Label(dialog, text="Новий пароль:").pack(anchor="w", padx=20, pady=(5, 0))
        pwd_entry = ttk.Entry(dialog, show="*", width=30)
        pwd_entry.pack(padx=20, pady=5)

        def apply_change():
            target_user = user_select.get() if is_admin else self.current_user
            new_pwd = pwd_entry.get()

            target_is_complex = self.db[target_user].get("is_complex", False)
            valid, msg = validate_password(new_pwd, target_is_complex)
            if not valid:
                messagebox.showerror("Error", msg, parent=dialog)
                return

            self.db[target_user]["password"] = new_pwd
            save_db(self.db)

            messagebox.showinfo("Info", f"Пароль для {target_user} змінено", parent=dialog)
            dialog.destroy()

        ttk.Button(dialog, text="Зберегти", command=apply_change).pack(pady=15)


if __name__ == "__main__":
    app = App()
    app.mainloop()