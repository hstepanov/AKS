import json
import os
import re
import shutil
import string
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

DATA_DIR = "Data"
LABELS_FILE = "resources_db.json"  # мітки конфіденційності ресурсів
DB_FILE = "users_db.json"
DEFAULT_USERS = ["Stepanov_1", "Stepanov_2", "Stepanov_3", "Stepanov_4", "Stepanov_5"]

# рівні доступу / мітки конфіденційності
ACCESS_LEVELS = {0: "Загальний доступ", 1: "Службове використання", 2: "Таємно", 3: "Цілком таємно"}
DEFAULT_USER_LEVEL = min(ACCESS_LEVELS)          # новий користувач — найнижчий рівень
DEFAULT_RESOURCE_LABEL = max(ACCESS_LEVELS)      # новий ресурс — "цілком таємно"

# початкові рівні доступу користувачів та мітки конфіденційності ресурсів
INITIAL_USER_LEVELS = {
    "Stepanov_1": 3,
    "Stepanov_2": 2,
    "Stepanov_3": 1,
    "Stepanov_4": 0,
    "Stepanov_5": 0,
}

INITIAL_RESOURCE_LABELS = {
    "doc1.txt": 0,
    "doc2.txt": 1,
    "doc3.txt": 2,
    "executable.sh": 2,
    "Stepan.jpeg": 3,
}

# редактори зображень. gimp - linux, open - macos
IMAGE_EDITORS = ["gimp", "open"]


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
                "is_admin": (i == 0)  # адмін - перший користувач в DEFAULT_USERS
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


# Функції мандатного розмежування доступу
def level_name(level: int) -> str:
    return f"{level} — {ACCESS_LEVELS.get(level, '?')}"


def validate_level(level) -> int:
    level = int(level)
    if level not in ACCESS_LEVELS:
        raise ValueError(f"Невідомий рівень доступу: {level}")
    return level

#Завантаження міток ресурсів; при першому запуску — налаштування політики.
def load_labels() -> dict:
    if not os.path.exists(LABELS_FILE):
        setup_mandatory_policy()
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_labels(labels: dict):
    with open(LABELS_FILE, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=4)


def get_user_level(db: dict, user: str) -> int:
    return db[user].get("access_level", DEFAULT_USER_LEVEL)


#Присвоєння рівня доступу користувачу
def set_user_level(db: dict, user: str, level, save: bool = True):
    if user not in db:
        raise KeyError(f"Користувача {user} не знайдено")
    db[user]["access_level"] = validate_level(level)
    if save:
        save_db(db)


def get_resource_label(labels: dict, resource: str) -> int:
    return labels.get(resource, DEFAULT_RESOURCE_LABEL)


# Присвоєння мітки конфіденційності ресурсу
def set_resource_label(labels: dict, resource: str, level, save: bool = True):
    if not os.path.isfile(os.path.join(DATA_DIR, resource)):
        raise FileNotFoundError(f"Ресурс {resource} не знайдено в {DATA_DIR}")
    labels[resource] = validate_level(level)
    if save:
        save_labels(labels)


# Синхронізація міток з вмістом Data (новим ресурсам мітка за замовчуванням, видалені ресурси прибираються)
def sync_resources(labels: dict, save: bool = True) -> dict:
    files = {f for f in os.listdir(DATA_DIR) if os.path.isfile(os.path.join(DATA_DIR, f))}
    for name in files - labels.keys():
        labels[name] = DEFAULT_RESOURCE_LABEL
    for name in labels.keys() - files:
        del labels[name]
    if save:
        save_labels(labels)
    return labels


    # Правило: повний доступ, якщо рівень користувача >= мітки ресурсу.
def check_access(db: dict, labels: dict, user: str, resource: str) -> bool:
    if user not in db or resource not in labels:
        return False
    return get_user_level(db, user) >= labels[resource]


def _require_access(db, labels, user, resource) -> str:
    if not check_access(db, labels, user, resource):
        raise PermissionError(
            f"Для цього ресурсу потрібен виший рівень доступу. Поточний рівень: ({level_name(get_user_level(db, user)) if user in db else '-'}) "
        )
    return os.path.join(DATA_DIR, resource)


def read_resource(db, labels, user, resource, binary: bool = False):
    path = _require_access(db, labels, user, resource)
    if binary:
        with open(path, "rb") as f:
            return f.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_resource(db, labels, user, resource, content):
    path = _require_access(db, labels, user, resource)
    if isinstance(content, bytes):
        with open(path, "wb") as f:
            f.write(content)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def execute_resource(db, labels, user, resource) -> subprocess.CompletedProcess:
    path = _require_access(db, labels, user, resource)
    return subprocess.run(["bash", path], capture_output=True, text=True, timeout=10)


def open_image_resource(db, labels, user, resource) -> str:
    """Відкриття зображення у зовнішньому редакторі (перегляд/редагування/збереження)."""
    path = _require_access(db, labels, user, resource)
    editor = next((e for e in IMAGE_EDITORS if shutil.which(e)), "xdg-open")
    subprocess.Popen([editor, os.path.abspath(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return editor


#Налаштування спроектованих правил (рівні користувачів і мітки ресурсів)
def setup_mandatory_policy():
    db = load_db()
    for user in db:
        level = INITIAL_USER_LEVELS.get(user, db[user].get("access_level", DEFAULT_USER_LEVEL))
        set_user_level(db, user, level, save=False)
    save_db(db)

    labels = {}
    if os.path.exists(LABELS_FILE):
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            labels = json.load(f)
    labels.update(INITIAL_RESOURCE_LABELS)
    sync_resources(labels)  # нові файли з Data отримають мітку за замовчуванням


# Перевірка коректності та дієвості правил
# Очікувана матриця доступу (користувач -> доступні ресурси)
EXPECTED_MATRIX = {
    "Stepanov_1": {"doc1.txt", "doc2.txt", "doc3.txt", "executable.sh", "Stepan.jpg"},
    "Stepanov_2": {"doc1.txt", "doc2.txt", "doc3.txt", "executable.sh"},
    "Stepanov_3": {"doc1.txt", "doc2.txt"},
    "Stepanov_4": {"doc1.txt"},
    "Stepanov_5": {"doc1.txt"},
}


# Спроба повного доступу через захищені операції
def _full_access_attempt(db, labels, user, resource):
    if resource.endswith(".sh"):
        execute_resource(db, labels, user, resource)
    else:
        binary = not resource.endswith(".txt")
        data = read_resource(db, labels, user, resource, binary=binary)
        write_resource(db, labels, user, resource, data)  # запис того самого вмісту


def test_policy_matrix(db, labels) -> list: # Рішення check_access збігаються з очікуваною матрицею.
    results = []
    for user, allowed in EXPECTED_MATRIX.items():
        for resource in INITIAL_RESOURCE_LABELS:
            expected = resource in allowed
            actual = check_access(db, labels, user, resource)
            status = "PASS" if actual == expected else "FAIL"
            results.append(f"[{status}] check_access {user} -> {resource}: "
                           f"очікувано {expected}, отримано {actual}")
    return results


# дозволені дії виконуються, заборонені дають PermissionError.
def test_real_operations(db, labels) -> list:
    results = []
    for user, allowed in EXPECTED_MATRIX.items():
        for resource in INITIAL_RESOURCE_LABELS:
            expected = resource in allowed
            try:
                _full_access_attempt(db, labels, user, resource)
                actual, note = True, "виконано"
            except PermissionError:
                actual, note = False, "PermissionError"
            except Exception as e:
                actual, note = None, f"помилка: {e}"
            status = "PASS" if actual == expected else "FAIL"
            results.append(f"[{status}] операція {user} -> {resource}: {note}")
    return results


def test_new_entities(db, labels) -> list: # Мітки для нових користувачів/ресурсів, некоректні рівні, невідомі суб'єкти.
    results = []
    db = json.loads(json.dumps(db))  # копії, щоб не змінювати реальні дані
    labels = dict(labels)

    def check(cond, msg):
        results.append(f"[{'PASS' if cond else 'FAIL'}] {msg}")

    db["__test_user__"] = {"password": "x", "is_complex": False, "is_admin": False}
    check(get_user_level(db, "__test_user__") == DEFAULT_USER_LEVEL,
          "новий користувач без мітки отримує найнижчий рівень")
    set_user_level(db, "__test_user__", 2, save=False)
    check(get_user_level(db, "__test_user__") == 2, "присвоєння рівня новому користувачу")

    try:
        set_user_level(db, "__test_user__", 99, save=False)
        check(False, "некоректний рівень відхиляється")
    except ValueError:
        check(True, "некоректний рівень відхиляється")

    check(not check_access(db, labels, "__unknown__", "doc1.txt"),
          "невідомому користувачу доступ заборонено")
    check(not check_access(db, labels, "Stepanov_1", "__unknown__.txt"),
          "доступ до невідомого ресурсу заборонено")

    tmp_name = "__test_resource__.txt"
    tmp_path = os.path.join(DATA_DIR, tmp_name)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("test")
        sync_resources(labels, save=False)
        check(labels.get(tmp_name) == DEFAULT_RESOURCE_LABEL,
              "новий ресурс отримує найвищу мітку")
        check(check_access(db, labels, "Stepanov_1", tmp_name)
              and not check_access(db, labels, "Stepanov_2", tmp_name),
              "новий ресурс доступний лише найвищому рівню")
        set_resource_label(labels, tmp_name, 1, save=False)
        check(check_access(db, labels, "Stepanov_3", tmp_name)
              and not check_access(db, labels, "Stepanov_4", tmp_name),
              "зміна мітки ресурсу змінює доступ")
    finally:
        os.remove(tmp_path)
    return results


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

            # Керування мітками та перевірка правил доступу лише для адміна
            ttk.Button(frame, text="Мандатні мітки", command=self.open_labels_dialog, width=30).pack(pady=5)

        ttk.Button(frame, text="Ресурси", command=self.open_resources_dialog, width=30).pack(pady=5)

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
        dialog.geometry("380x380")
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

        # Рівень доступу нового користувача (MAC)
        ttk.Label(dialog, text="Рівень доступу").pack(anchor="w", padx=20, pady=(5, 0))
        level_select = ttk.Combobox(dialog, values=[level_name(l) for l in ACCESS_LEVELS],
                                    state="readonly", width=28)
        level_select.current(DEFAULT_USER_LEVEL)
        level_select.pack(padx=20, pady=5)

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
                "is_admin": is_admin,
                "access_level": validate_level(level_select.current())
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

    # --- Ресурси з мандатним розмежуванням доступу
    def open_resources_dialog(self):
        labels = sync_resources(load_labels())

        dialog = tk.Toplevel(self)
        dialog.title("Ресурси")
        dialog.geometry("520x300")
        dialog.grab_set()

        user_level = get_user_level(self.db, self.current_user)
        ttk.Label(dialog, text=f"Ваш рівень доступу: {level_name(user_level)}").pack(pady=(10, 0))

        tree = ttk.Treeview(dialog, columns=("label", "access"), height=8)
        tree.heading("#0", text="Ресурс")
        tree.heading("label", text="Мітка")
        tree.heading("access", text="Доступ")
        tree.column("#0", width=160)
        tree.column("label", width=170)
        tree.column("access", width=140)
        for name in sorted(labels):
            access = "повний" if check_access(self.db, labels, self.current_user, name) else "заборонено"
            tree.insert("", "end", iid=name, text=name, values=(level_name(labels[name]), access))
        tree.pack(padx=10, pady=10, fill="both", expand=True)

        def open_selected():
            if not tree.selection():
                return
            name = tree.selection()[0]
            try:
                if name.endswith(".sh"):
                    res = execute_resource(self.db, labels, self.current_user, name)
                    messagebox.showinfo(name, f"Код: {res.returncode}\n\n{res.stdout}{res.stderr}", parent=dialog)
                elif name.endswith(".txt"):
                    self.open_text_editor(labels, name)
                else:
                    editor = open_image_resource(self.db, labels, self.current_user, name)
            except PermissionError as e:
                messagebox.showerror("Доступ заборонено", str(e), parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        ttk.Button(dialog, text="Відкрити", command=open_selected).pack(pady=(0, 10))

    def open_text_editor(self, labels: dict, name: str):
        content = read_resource(self.db, labels, self.current_user, name)

        editor = tk.Toplevel(self)
        editor.title(name)
        editor.geometry("520x400")
        editor.grab_set()

        text = tk.Text(editor, wrap="word")
        text.insert("1.0", content)
        text.pack(fill="both", expand=True, padx=10, pady=10)

        def save():
            try:
                write_resource(self.db, labels, self.current_user, name, text.get("1.0", "end-1c"))
                messagebox.showinfo("Info", f"{name} збережено", parent=editor)
            except PermissionError as e:
                messagebox.showerror("Доступ заборонено", str(e), parent=editor)

        ttk.Button(editor, text="Зберегти", command=save).pack(pady=(0, 10))

    # Присвоєння рівнів користувачам і міток ресурсам (адмін)
    def open_labels_dialog(self):
        labels = sync_resources(load_labels())
        level_values = [level_name(l) for l in ACCESS_LEVELS]

        dialog = tk.Toplevel(self)
        dialog.title("Мандатні мітки")
        dialog.geometry("420x330")
        dialog.grab_set()

        ttk.Label(dialog, text="Рівень доступу користувача", font=("Arial", 11, "bold")).pack(pady=(10, 0))
        user_select = ttk.Combobox(dialog, values=list(self.db.keys()), state="readonly", width=30)
        user_level_select = ttk.Combobox(dialog, values=level_values, state="readonly", width=30)
        user_select.bind("<<ComboboxSelected>>",
                         lambda e: user_level_select.current(get_user_level(self.db, user_select.get())))
        user_select.pack(pady=3)
        user_level_select.pack(pady=3)

        def apply_user():
            if user_select.get() and user_level_select.get():
                set_user_level(self.db, user_select.get(), user_level_select.current())
                messagebox.showinfo("Info", "Рівень користувача збережено", parent=dialog)

        ttk.Button(dialog, text="Зберегти рівень", command=apply_user).pack(pady=5)

        ttk.Label(dialog, text="Мітка конфіденційності ресурсу", font=("Arial", 11, "bold")).pack(pady=(10, 0))
        res_select = ttk.Combobox(dialog, values=sorted(labels), state="readonly", width=30)
        res_level_select = ttk.Combobox(dialog, values=level_values, state="readonly", width=30)
        res_select.bind("<<ComboboxSelected>>",
                        lambda e: res_level_select.current(get_resource_label(labels, res_select.get())))
        res_select.pack(pady=3)
        res_level_select.pack(pady=3)

        def apply_resource():
            if res_select.get() and res_level_select.get():
                set_resource_label(labels, res_select.get(), res_level_select.current())
                messagebox.showinfo("Info", "Мітку ресурсу збережено", parent=dialog)

        ttk.Button(dialog, text="Зберегти мітку", command=apply_resource).pack(pady=5)


if __name__ == "__main__":
    load_labels()  # при першому запуску налаштовує політику
    app = App()
    app.mainloop()