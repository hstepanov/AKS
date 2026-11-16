import functools
import json
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

DATA_DIR = "Data"
LABELS_FILE = "resources_db.json"  # мітки конфіденційності ресурсів (MAC)
ACL_FILE = "acl_db.json"           # матриця доступу (DAC)
SETTINGS_FILE = "settings.json"    # нобрана модель доступу знаходиться тут
DB_FILE = "users_db.json"
DEFAULT_USERS = ["Stepanov_1", "Stepanov_2", "Stepanov_3", "Stepanov_4", "Stepanov_5"]

# редактори зображень. gimp - linux, open - macos
IMAGE_EDITORS = ["gimp", "open"]


# =====================================================================================
# Створення та ініціалізація бази даних JSON з 5 юзерами.
# Stepanov_1 -> адмін (is_admin = True), решта - звичайні юзери.
# =====================================================================================

def init_db():
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
        messagebox.showerror("Error", f"Не вдалося завантажити БД: {e}")
        return {}


def save_db(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def is_admin(db: dict, user: str) -> bool:
    return bool(db.get(user, {}).get("is_admin", False))


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


def list_data_files() -> set:
    return {f for f in os.listdir(DATA_DIR)
            if os.path.isfile(os.path.join(DATA_DIR, f)) and not f.startswith(".")}


# =====================================================================================
# Налаштування технології розмежування доступу
# =====================================================================================
MANDATORY = "mandatory"
DISCRETIONARY = "discretionary"
ROLE_BASED = "role_based"

ACCESS_MODELS = {
    MANDATORY: "Мандатне розмежування доступу",
    DISCRETIONARY: "Дискреційне розмежування доступу",
    ROLE_BASED: "Рольове розмежування доступу",
}
DEFAULT_ACCESS_MODEL = DISCRETIONARY


class AccessModelError(PermissionError):
    """Функція викликана при іншій обраній моделі розмежування доступу."""


def load_settings() -> dict:
    settings = {"access_model": DEFAULT_ACCESS_MODEL}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    if settings["access_model"] not in ACCESS_MODELS:
        settings["access_model"] = DEFAULT_ACCESS_MODEL
    return settings


def init_settings():
    """Створення settings.json з моделлю за замовчуванням при першому запуску."""
    if not os.path.exists(SETTINGS_FILE):
        save_settings(load_settings())


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


def get_access_model() -> str:
    return load_settings()["access_model"]


def set_access_model(model: str):
    if model not in ACCESS_MODELS:
        raise ValueError(f"Невідома модель розмежування доступу: {model}")
    settings = load_settings()
    settings["access_model"] = model
    save_settings(settings)


# Декоратор, функція виконується лише при обраній у налаштуваннях моделі model
def requires_model(model: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current = get_access_model()
            if current != model:
                raise AccessModelError(
                    f"Функція {func.__name__} доступна лише при моделі "
                    f"\"{ACCESS_MODELS[model]}\". Поточна модель: \"{ACCESS_MODELS[current]}\"."
                )
            return func(*args, **kwargs)
        wrapper.access_model = model
        return wrapper
    return decorator


# =====================================================================================
# Мандатне розмежування доступу. функції з lab2, виконуються лише в режимі MAC
# =====================================================================================
ACCESS_LEVELS = {0: "Відкрито", 1: "ДСК", 2: "Таємно", 3: "Цілком таємно"}
DEFAULT_USER_LEVEL = min(ACCESS_LEVELS)          # новий користувач — найнижчий рівень (відкрито)
DEFAULT_RESOURCE_LABEL = max(ACCESS_LEVELS)      # новий ресурс — "цілком таємно"

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


@requires_model(MANDATORY)
def mac_level_name(level: int) -> str:
    return f"{level} — {ACCESS_LEVELS.get(level, '?')}"


@requires_model(MANDATORY)
def mac_validate_level(level) -> int:
    level = int(level)
    if level not in ACCESS_LEVELS:
        raise ValueError(f"Невідомий рівень доступу: {level}")
    return level


# Завантаження міток ресурсів; при першому запуску — налаштування політики.
@requires_model(MANDATORY)
def mac_load_labels() -> dict:
    if not os.path.exists(LABELS_FILE):
        mac_setup_policy()
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@requires_model(MANDATORY)
def mac_save_labels(labels: dict):
    with open(LABELS_FILE, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=4)


@requires_model(MANDATORY)
def mac_get_user_level(db: dict, user: str) -> int:
    return db[user].get("access_level", DEFAULT_USER_LEVEL)


# Присвоєння рівня доступу користувачу
@requires_model(MANDATORY)
def mac_set_user_level(db: dict, user: str, level, save: bool = True):
    if user not in db:
        raise KeyError(f"Користувача {user} не знайдено")
    db[user]["access_level"] = mac_validate_level(level)
    if save:
        save_db(db)


@requires_model(MANDATORY)
def mac_get_resource_label(labels: dict, resource: str) -> int:
    return labels.get(resource, DEFAULT_RESOURCE_LABEL)


# Присвоєння мітки конфіденційності ресурсу
@requires_model(MANDATORY)
def mac_set_resource_label(labels: dict, resource: str, level, save: bool = True):
    if not os.path.isfile(os.path.join(DATA_DIR, resource)):
        raise FileNotFoundError(f"Ресурс {resource} не знайдено в {DATA_DIR}")
    labels[resource] = mac_validate_level(level)
    if save:
        mac_save_labels(labels)


# Синхронізація міток з вмістом Data
@requires_model(MANDATORY)
def mac_sync_resources(labels: dict, save: bool = True) -> dict:
    files = list_data_files()
    for name in files - labels.keys():
        labels[name] = DEFAULT_RESOURCE_LABEL
    for name in labels.keys() - files:
        del labels[name]
    if save:
        mac_save_labels(labels)
    return labels


# Правило: повний доступ, якщо рівень користувача >= мітки ресурсу.
@requires_model(MANDATORY)
def mac_check_access(db: dict, labels: dict, user: str, resource: str) -> bool:
    if user not in db or resource not in labels:
        return False
    return mac_get_user_level(db, user) >= labels[resource]


@requires_model(MANDATORY)
def _mac_require_access(db, labels, user, resource) -> str:
    if not mac_check_access(db, labels, user, resource):
        current = mac_level_name(mac_get_user_level(db, user)) if user in db else "-"
        raise PermissionError(
            f"Для цього ресурсу потрібен виший рівень доступу. Поточний рівень: ({current})"
        )
    return os.path.join(DATA_DIR, resource)


@requires_model(MANDATORY)
def mac_read_resource(db, labels, user, resource, binary: bool = False):
    path = _mac_require_access(db, labels, user, resource)
    if binary:
        with open(path, "rb") as f:
            return f.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@requires_model(MANDATORY)
def mac_write_resource(db, labels, user, resource, content):
    path = _mac_require_access(db, labels, user, resource)
    if isinstance(content, bytes):
        with open(path, "wb") as f:
            f.write(content)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


@requires_model(MANDATORY)
def mac_execute_resource(db, labels, user, resource) -> subprocess.CompletedProcess:
    path = _mac_require_access(db, labels, user, resource)
    return subprocess.run(["bash", path], capture_output=True, text=True, timeout=10)


@requires_model(MANDATORY)
def mac_open_image_resource(db, labels, user, resource) -> str:
    """Відкриття зображення у зовнішньому редакторі (перегляд/редагування/збереження)."""
    path = _mac_require_access(db, labels, user, resource)
    editor = next((e for e in IMAGE_EDITORS if shutil.which(e)), "xdg-open")
    subprocess.Popen([editor, os.path.abspath(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return editor


# Налаштування правил (рівні користувачів і мітки ресурсів)
@requires_model(MANDATORY)
def mac_setup_policy():
    db = load_db()
    for user in db:
        level = INITIAL_USER_LEVELS.get(user, db[user].get("access_level", DEFAULT_USER_LEVEL))
        mac_set_user_level(db, user, level, save=False)
    save_db(db)

    labels = {}
    if os.path.exists(LABELS_FILE):
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            labels = json.load(f)
    labels.update(INITIAL_RESOURCE_LABELS)
    mac_sync_resources(labels)  # нові файли з Data отримають мітку за замовчуванням


# =====================================================================================
# Дискреційне розмежування доступу. виконується лише в режимі DAC
# =====================================================================================
RIGHT_READ, RIGHT_WRITE, RIGHT_EXEC = "r", "w", "x"
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
WORKDAYS = [0, 1, 2, 3, 4]
INITIAL_OWNER = "Stepanov_1"


def _entry(rights, time=None, days=None, expires=None) -> dict:
    return {"rights": rights, "time": list(time) if time else None,
            "days": list(days) if days else None, "expires": expires}


# Спроектована матриця доступу. без власника — його права неявні
INITIAL_ACL = {
    "doc1.txt": {
        "owner": INITIAL_OWNER,
        "acl": {
            "Stepanov_2": _entry("rw", ("08:00", "20:00")),
            "Stepanov_3": _entry("rw", ("09:00", "18:00")),
            "Stepanov_4": _entry("r", ("09:00", "18:00")),
            "Stepanov_5": _entry("r", ("10:00", "16:00"), WORKDAYS, "2026-12-31"),
        },
    },
    "doc2.txt": {
        "owner": INITIAL_OWNER,
        "acl": {
            "Stepanov_2": _entry("rw", ("08:00", "20:00"), WORKDAYS),
            "Stepanov_3": _entry("r", ("09:00", "18:00")),
            "Stepanov_4": _entry("r", ("09:00", "18:00"), WORKDAYS),
        },
    },
    "doc3.txt": {
        "owner": INITIAL_OWNER,
        "acl": {
            "Stepanov_2": _entry("r", ("08:00", "20:00")),
        },
    },
    "executable.sh": {
        "owner": INITIAL_OWNER,
        "acl": {
            "Stepanov_2": _entry("x", ("09:00", "18:00")),
            "Stepanov_3": _entry("x", ("09:00", "18:00"), WORKDAYS),
        },
    },
    "Stepan.jpeg": {
        "owner": INITIAL_OWNER,
        "acl": {
            "Stepanov_2": _entry("r", ("08:00", "20:00")),
            "Stepanov_3": _entry("r", ("09:00", "18:00")),
        },
    },
}

# Базовий шаблон прав, який адмін може надати новому користувачу
DEFAULT_NEW_USER_ACL = {"doc1.txt": _entry("r", ("09:00", "18:00"), WORKDAYS)}

EXECUTABLE_EXT = (".sh",)
TEXT_EXT = (".txt",)

# Допустимі права для типу ресурсу
def rights_for_type(resource: str) -> str:
    if resource.endswith(EXECUTABLE_EXT):
        return RIGHT_WRITE + RIGHT_EXEC  # редагування, виконання
    return RIGHT_READ + RIGHT_WRITE      # перегляд, редагування та збереження


def right_title(resource: str, right: str) -> str:
    if right == RIGHT_READ:
        return "перегляд"
    if right == RIGHT_WRITE:
        return "редагування" if resource.endswith(EXECUTABLE_EXT) else "редагування/збереження"
    if right == RIGHT_EXEC:
        return "виконання"
    return right


def restrictions_text(entry: dict) -> str:
    parts = []
    if entry.get("time"):
        parts.append(f"{entry['time'][0]}-{entry['time'][1]}")
    if entry.get("days"):
        parts.append(",".join(WEEKDAYS[d] for d in entry["days"]))
    if entry.get("expires"):
        parts.append(f"до {entry['expires']}")
    return "; ".join(parts) if parts else "без обмежень"


def _parse_time(value: str) -> str:
    return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M")


# Перевірка коректності запису ACL
def _normalize_entry(resource: str, rights: str, time=None, days=None, expires=None) -> dict:
    allowed = rights_for_type(resource)
    bad = set(rights) - set(allowed)
    if bad:
        raise ValueError(f"Права {bad} недопустимі для {resource} (допустимі: {allowed})")
    rights = "".join(r for r in allowed if r in set(rights))  # канонічний порядок
    if time:
        if len(time) != 2:
            raise ValueError("Часове обмеження задається як (початок, кінець)")
        time = (_parse_time(time[0]), _parse_time(time[1]))
        if time[0] == time[1]:
            raise ValueError("Початок і кінець часового вікна збігаються")
    if days:
        days = sorted(set(int(d) for d in days))
        if any(d not in range(7) for d in days):
            raise ValueError("Дні тижня задаються числами 0 (Пн) - 6 (Нд)")
    if expires:
        expires = date.fromisoformat(expires.strip()).isoformat()
    return _entry(rights, time, days, expires or None)


# перевірка обмежень запису - час, дні тижня, термін дії
def _entry_active(entry: dict, now: datetime) -> tuple[bool, str]:
    if entry.get("expires") and now.date() > date.fromisoformat(entry["expires"]):
        return False, f"термін дії прав минув {entry['expires']}"
    if entry.get("days") and now.weekday() not in entry["days"]:
        return False, "доступ заборонено в цей день тижня"
    if entry.get("time"):
        start, end = entry["time"]
        cur = now.strftime("%H:%M")
        inside = start <= cur < end if start < end else (cur >= start or cur < end)
        if not inside:
            return False, f"доступ дозволено лише з {start} до {end}"
    return True, ""


@requires_model(DISCRETIONARY)
def dac_save_acl(acl: dict):
    with open(ACL_FILE, "w", encoding="utf-8") as f:
        json.dump(acl, f, ensure_ascii=False, indent=4)


# налаштовуємо матрицю доступу
@requires_model(DISCRETIONARY)
def dac_setup_policy(db: dict | None = None) -> dict:
    db = db if db is not None else load_db()
    acl = json.loads(json.dumps(INITIAL_ACL))
    dac_sync(acl, db)
    return acl


# Завантаження матриці доступу, налаштовуємо політику при першому запуску
@requires_model(DISCRETIONARY)
def dac_load_acl() -> dict:
    if not os.path.exists(ACL_FILE):
        return dac_setup_policy()
    with open(ACL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@requires_model(DISCRETIONARY)
def dac_default_owner(db: dict) -> str | None:
    if is_admin(db, INITIAL_OWNER):
        return INITIAL_OWNER
    return next((u for u in db if is_admin(db, u)), None)


# Синхронізація матриці з ресурсами в Data та користувачами в БД
# Новий ресурс -> власник адміністратор (або owner), інші користувачі без прав
# зниклі ресурси та видалені користувачі прибираються з матриці.
@requires_model(DISCRETIONARY)
def dac_sync(acl: dict, db: dict, owner: str | None = None, save: bool = True) -> dict:
    files = list_data_files()
    default_owner = owner or dac_default_owner(db)
    for name in files - acl.keys():
        acl[name] = {"owner": default_owner, "acl": {}}
    for name in acl.keys() - files:
        del acl[name]
    for res in acl.values():
        if res.get("owner") not in db:
            res["owner"] = default_owner
        res["acl"] = {u: e for u, e in res.get("acl", {}).items() if u in db and u != res["owner"]}
    if save:
        dac_save_acl(acl)
    return acl


# Запис матриці доступу (для власника — повні права без обмежень)
@requires_model(DISCRETIONARY)
def dac_get_entry(acl: dict, user: str, resource: str) -> dict | None:
    if resource not in acl:
        return None
    if acl[resource].get("owner") == user:
        return _entry(rights_for_type(resource))
    return acl[resource]["acl"].get(user)


@requires_model(DISCRETIONARY) # Рішення про доступ та причина відмови
def dac_access_decision(db: dict, acl: dict, user: str, resource: str, right: str,
                        now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now()
    if user not in db:
        return False, "невідомий користувач"
    if resource not in acl:
        return False, "ресурс відсутній у матриці доступу"
    if right not in rights_for_type(resource):
        return False, f"право '{right}' не застосовне до {resource}"
    entry = dac_get_entry(acl, user, resource)
    if not entry or right not in entry["rights"]:
        return False, f"немає права \"{right_title(resource, right)}\""
    return _entry_active(entry, now)


@requires_model(DISCRETIONARY)
def dac_check_access(db: dict, acl: dict, user: str, resource: str, right: str,
                     now: datetime | None = None) -> bool:
    return dac_access_decision(db, acl, user, resource, right, now)[0]


@requires_model(DISCRETIONARY)
def _dac_require(db, acl, user, resource, right, now=None) -> str:
    allowed, reason = dac_access_decision(db, acl, user, resource, right, now)
    if not allowed:
        raise PermissionError(f"Доступ до {resource} заборонено: {reason}")
    return os.path.join(DATA_DIR, resource)


@requires_model(DISCRETIONARY)
def dac_read_resource(db, acl, user, resource, binary: bool = False, now=None):
    path = _dac_require(db, acl, user, resource, RIGHT_READ, now)
    with open(path, "rb" if binary else "r", **({} if binary else {"encoding": "utf-8"})) as f:
        return f.read()


@requires_model(DISCRETIONARY) # Завантаження вмісту для редагування
def dac_load_for_edit(db, acl, user, resource, now=None) -> str:
    path = _dac_require(db, acl, user, resource, RIGHT_WRITE, now)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@requires_model(DISCRETIONARY)
def dac_write_resource(db, acl, user, resource, content, now=None):
    path = _dac_require(db, acl, user, resource, RIGHT_WRITE, now)
    if isinstance(content, bytes):
        with open(path, "wb") as f:
            f.write(content)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


@requires_model(DISCRETIONARY)
def dac_execute_resource(db, acl, user, resource, now=None) -> subprocess.CompletedProcess:
    path = _dac_require(db, acl, user, resource, RIGHT_EXEC, now)
    return subprocess.run(["bash", path], capture_output=True, text=True, timeout=10)


# Перегляд або редагування зі збереженням зображення.
# При перегляді відкривається тимчасова копія, зміни не потрапляють в оригінал.
@requires_model(DISCRETIONARY)
def dac_open_image(db, acl, user, resource, edit: bool = False, now=None) -> str:
    if edit:
        path = os.path.abspath(_dac_require(db, acl, user, resource, RIGHT_WRITE, now))
        editor = next((e for e in IMAGE_EDITORS if shutil.which(e)), "xdg-open")
    else:
        src = _dac_require(db, acl, user, resource, RIGHT_READ, now)
        path = os.path.join(tempfile.mkdtemp(prefix="dac_view_"), resource)
        shutil.copyfile(src, path)
        os.chmod(path, 0o444)
        editor = "open" if shutil.which("open") else "xdg-open"
    subprocess.Popen([editor, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return editor


# --- Керування правами: власник ресурсу або адміністратор
@requires_model(DISCRETIONARY)
def dac_can_manage(db: dict, acl: dict, actor: str, resource: str) -> bool:
    return resource in acl and (acl[resource].get("owner") == actor or is_admin(db, actor))


@requires_model(DISCRETIONARY)
def _dac_require_manage(db, acl, actor, resource, user=None):
    if resource not in acl:
        raise KeyError(f"Ресурс {resource} відсутній у матриці доступу")
    if user is not None and user not in db:
        raise KeyError(f"Користувача {user} не знайдено")
    if not dac_can_manage(db, acl, actor, resource):
        raise PermissionError(f"{actor} не є власником {resource} і не може керувати правами")


# Надання / зміна прав користувача на ресурс з обмеженнями
@requires_model(DISCRETIONARY)
def dac_grant(db, acl, actor, user, resource, rights, time=None, days=None, expires=None,
              save: bool = True) -> dict:
    _dac_require_manage(db, acl, actor, resource, user)
    if acl[resource]["owner"] == user:
        raise ValueError(f"{user} є власником {resource} і вже має всі права")
    entry = _normalize_entry(resource, rights, time, days, expires)
    if entry["rights"]:
        acl[resource]["acl"][user] = entry
    else:
        acl[resource]["acl"].pop(user, None)
    if save:
        dac_save_acl(acl)
    return entry


# Відкликання всіх прав (rights=None) або окремих прав користувача
@requires_model(DISCRETIONARY)
def dac_revoke(db, acl, actor, user, resource, rights: str | None = None, save: bool = True):
    _dac_require_manage(db, acl, actor, resource, user)
    entry = acl[resource]["acl"].get(user)
    if entry:
        remaining = "" if rights is None else "".join(r for r in entry["rights"] if r not in rights)
        if remaining:
            entry["rights"] = remaining
        else:
            del acl[resource]["acl"][user]
    if save:
        dac_save_acl(acl)


# Передача права власності на ресурс
@requires_model(DISCRETIONARY)
def dac_set_owner(db, acl, actor, new_owner, resource, save: bool = True):
    _dac_require_manage(db, acl, actor, resource, new_owner)
    old_owner = acl[resource]["owner"]
    acl[resource]["owner"] = new_owner
    acl[resource]["acl"].pop(new_owner, None)
    if old_owner in db and old_owner != new_owner:
        # попередній власник зберігає повні права, але вже як звичайний запис
        acl[resource]["acl"][old_owner] = _entry(rights_for_type(resource))
    if save:
        dac_save_acl(acl)


# Реєстрація нового користувача в матриці: без прав або з шаблоном прав.
@requires_model(DISCRETIONARY)
def dac_add_user(db, acl, actor, user, template: dict | None = None, save: bool = True):
    if not is_admin(db, actor):
        raise PermissionError("Додавати користувачів може лише адміністратор")
    dac_sync(acl, db, save=False)
    for resource, entry in (template or {}).items():
        if resource in acl:
            dac_grant(db, acl, actor, user, resource, entry["rights"], entry.get("time"),
                      entry.get("days"), entry.get("expires"), save=False)
    if save:
        dac_save_acl(acl)


# перелік можливостей користувача: рядок матриці.
@requires_model(DISCRETIONARY)
def dac_user_rights(acl: dict, user: str) -> dict:
    result = {}
    for resource in sorted(acl):
        entry = dac_get_entry(acl, user, resource)
        if entry:
            result[resource] = entry
    return result


# Відображення матриці та списків доступу
def _cell(acl: dict, user: str, resource: str) -> str:
    if acl[resource].get("owner") == user:
        return f"O ({rights_for_type(resource)})"
    entry = acl[resource]["acl"].get(user)
    if not entry:
        return "-"
    restr = restrictions_text(entry)
    return entry["rights"] + ("" if restr == "без обмежень" else f" [{restr}]")


@requires_model(DISCRETIONARY)
def dac_matrix_rows(db: dict, acl: dict) -> tuple[list, list]:
    resources = [r for r in INITIAL_ACL if r in acl] + sorted(set(acl) - INITIAL_ACL.keys())
    rows = [[user] + [_cell(acl, user, r) for r in resources] for user in db]
    return ["Користувач"] + resources, rows


@requires_model(DISCRETIONARY)
def dac_matrix_text(db: dict, acl: dict) -> str:
    header, rows = dac_matrix_rows(db, acl)
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = lambda row: "| " + " | ".join(str(c).ljust(w) for c, w in zip(row, widths)) + " |"
    lines = [sep, fmt(header), sep] + [fmt(r) for r in rows] + [sep]
    lines.append("O - власник (усі права + керує правами інших)")
    return "\n".join(lines)


@requires_model(DISCRETIONARY)
def dac_acl_lists_text(acl: dict) -> str:
    lines = []
    for resource in sorted(acl):
        lines.append(f"{resource} (власник: {acl[resource]['owner']}):")
        if not acl[resource]["acl"]:
            lines.append("    інші користувачі доступу не мають")
        for user, entry in acl[resource]["acl"].items():
            titles = ", ".join(right_title(resource, r) for r in entry["rights"])
            lines.append(f"    {user}: {titles} ({restrictions_text(entry)})")
    return "\n".join(lines)


# =====================================================================================
# Графічний інтерфейс
# =====================================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("AdmKS_Stepanov")
        self.geometry("480x460")
        self.resizable(False, False)

        self.configure(bg="#ececec")
        self.update_idletasks()

        self.current_user = None
        self.db = load_db()

        self.create_menu()
        self.build_auth_ui()

    # Меню
    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Модель розмежування доступу",
                                  command=self.open_access_model_dialog)
        menubar.add_cascade(label="Налаштування", menu=settings_menu)

        author_menu = tk.Menu(menubar, tearoff=0)
        author_menu.add_command(label="Про автора", command=self.show_author_info)
        menubar.add_cascade(label="Інформація", menu=author_menu)

    def show_author_info(self):
        messagebox.showinfo("Про автора", "KSDM-51, Mykola Stepanov")

    def clear_frame(self):
        for widget in self.winfo_children():
            if not isinstance(widget, tk.Menu):
                widget.destroy()

    def _is_admin(self) -> bool:
        return self.current_user is not None and is_admin(self.db, self.current_user)

    # Вибір технології розмежування доступу (лише адміністратор)
    def open_access_model_dialog(self):
        if not self._is_admin():
            messagebox.showerror("Error", "Змінювати налаштування може лише адміністратор "
                                          "(увійдіть в систему як адміністратор)")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Модель розмежування доступу")
        dialog.geometry("380x220")
        dialog.grab_set()

        model_var = tk.StringVar(value=get_access_model())
        ttk.Label(dialog, text="Технологія розмежування доступу:",
                  font=("Arial", 11, "bold")).pack(anchor="w", padx=20, pady=(15, 5))
        for key, title in ACCESS_MODELS.items():
            ttk.Radiobutton(dialog, text=title, value=key, variable=model_var).pack(anchor="w", padx=30)

        def apply():
            set_access_model(model_var.get())
            if model_var.get() == MANDATORY:
                mac_load_labels()          # при першому виборі налаштовує політику MAC
            elif model_var.get() == DISCRETIONARY:
                dac_sync(dac_load_acl(), self.db)
            self.db = load_db()
            messagebox.showinfo("Info", f"Обрано: {ACCESS_MODELS[model_var.get()]}", parent=dialog)
            dialog.destroy()
            self.build_dashboard_ui()

        ttk.Button(dialog, text="Зберегти", command=apply).pack(pady=15)

    # Автентифікація
    def build_auth_ui(self):
        self.current_user = None
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
            self.db = load_db()

            if user not in self.db:
                messagebox.showerror("Error", "Користувача не знайдено!")
                return

            if self.db[user]["password"] == pwd:
                self.current_user = user
                self.build_dashboard_ui()
            else:
                messagebox.showerror("Error", "Невірний пароль")

        ttk.Button(frame, text="Залогінитись", command=login).pack(pady=15)

    # Панель управління: набір функцій залежить від обраної моделі
    def build_dashboard_ui(self):
        self.clear_frame()

        frame = ttk.Frame(self, padding="20")
        frame.pack(expand=True, fill="both")

        admin = self._is_admin()
        model = get_access_model()

        ttk.Label(frame, text=f"Вітаю {self.current_user}", font=("Arial", 12, "bold"),
                  foreground="green", justify="center").pack(pady=(5, 0))
        ttk.Label(frame, text=f"Модель: {ACCESS_MODELS[model]}").pack(pady=(0, 10))

        def button(text, command):
            ttk.Button(frame, text=text, command=command, width=30).pack(pady=3)

        if admin:
            button("Модель розмежування доступу", self.open_access_model_dialog)
            button("Додати нового користувача", self.open_add_user_dialog)

        if model == MANDATORY:
            if admin:
                button("Мандатні мітки", self.open_labels_dialog)
            button("Ресурси", self.open_resources_dialog)
        elif model == DISCRETIONARY:
            button("Ресурси", self.open_dac_resources_dialog)
            acl = dac_sync(dac_load_acl(), self.db)
            if admin or any(dac_can_manage(self.db, acl, self.current_user, r) for r in acl):
                button("Керування правами доступу", self.open_dac_rights_dialog)
            button("Матриця доступу", self.open_dac_matrix_dialog)
        else:
            ttk.Label(frame, text="Рольове розмежування доступу\nбуде реалізовано "
                                  "в наступній лабі", justify="center",
                      foreground="gray").pack(pady=5)

        button("Змінити пароль", self.open_change_password_dialog)
        ttk.Button(frame, text="Вийти з акаунту", command=self.build_auth_ui, width=30).pack(pady=12)

    # Додати нового користувача
    def open_add_user_dialog(self):
        if not self._is_admin():
            messagebox.showerror("Error", "Цю дію може виконувати лише адміністратор")
            return

        model = get_access_model()
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
        ttk.Checkbutton(dialog, text="Необхідний складний пароль",
                        variable=is_complex_var).pack(anchor="w", padx=20, pady=5)

        is_admin_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="Адміністратор", variable=is_admin_var).pack(anchor="w", padx=20, pady=5)

        level_select = None
        template_var = tk.BooleanVar(value=False)
        if model == MANDATORY:
            ttk.Label(dialog, text="Рівень доступу").pack(anchor="w", padx=20, pady=(5, 0))
            level_select = ttk.Combobox(dialog, values=[mac_level_name(l) for l in ACCESS_LEVELS],
                                        state="readonly", width=28)
            level_select.current(DEFAULT_USER_LEVEL)
            level_select.pack(padx=20, pady=5)
        elif model == DISCRETIONARY:
            ttk.Checkbutton(dialog, text="Базові права (перегляд doc1.txt,\nПн-Пт 09:00-18:00)",
                            variable=template_var).pack(anchor="w", padx=20, pady=5)
            ttk.Label(dialog, text="Інакше користувач не матиме жодних прав\n"
                                   "(призначаються в \"Керування правами\")",
                      foreground="gray").pack(anchor="w", padx=20)

        def save_user():
            new_user = user_entry.get().strip()
            new_pwd = pwd_entry.get()
            is_complex = is_complex_var.get()

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

            self.db[new_user] = {"password": new_pwd, "is_complex": is_complex,
                                 "is_admin": is_admin_var.get()}
            if level_select is not None:
                self.db[new_user]["access_level"] = mac_validate_level(level_select.current())
            save_db(self.db)

            if model == DISCRETIONARY:
                dac_add_user(self.db, dac_load_acl(), self.current_user, new_user,
                             DEFAULT_NEW_USER_ACL if template_var.get() else None)

            messagebox.showinfo("Info", f"Користувач {new_user} доданий", parent=dialog)
            dialog.destroy()

        ttk.Button(dialog, text="Створити", command=save_user).pack(pady=15)

    # Зміна пароля
    def open_change_password_dialog(self):
        admin = self._is_admin()

        dialog = tk.Toplevel(self)
        dialog.title("Зміна пароля")
        dialog.geometry("380x300")
        dialog.grab_set()

        user_select = None
        if admin:
            ttk.Label(dialog, text="Оберіть користувача:").pack(anchor="w", padx=20, pady=(15, 0))
            user_select = ttk.Combobox(dialog, values=list(self.db.keys()), state="readonly", width=28)
            user_select.set(self.current_user)
            user_select.pack(padx=20, pady=5)
        else:
            ttk.Label(dialog, text=f"Користувач: {self.current_user}",
                      font=("Arial", 11, "bold")).pack(anchor="w", padx=20, pady=(15, 0))

        ttk.Label(dialog, text="Новий пароль:").pack(anchor="w", padx=20, pady=(5, 0))
        pwd_entry = ttk.Entry(dialog, show="*", width=30)
        pwd_entry.pack(padx=20, pady=5)

        def apply_change():
            target_user = user_select.get() if admin else self.current_user
            new_pwd = pwd_entry.get()

            valid, msg = validate_password(new_pwd, self.db[target_user].get("is_complex", False))
            if not valid:
                messagebox.showerror("Error", msg, parent=dialog)
                return

            self.db[target_user]["password"] = new_pwd
            save_db(self.db)
            messagebox.showinfo("Info", f"Пароль для {target_user} змінено", parent=dialog)
            dialog.destroy()

        ttk.Button(dialog, text="Зберегти", command=apply_change).pack(pady=15)

    # Вікно з текстом: редагування зі збереженням (on_save) або лише перегляд
    def _text_window(self, title: str, content: str, on_save=None):
        win = tk.Toplevel(self)
        win.title(title + ("" if on_save else " (лише перегляд)"))
        win.geometry("560x400")
        win.grab_set()

        text = tk.Text(win, wrap="word")
        text.insert("1.0", content)
        text.pack(fill="both", expand=True, padx=10, pady=10)

        if on_save is None:
            text.configure(state="disabled")
            return

        def save():
            try:
                on_save(text.get("1.0", "end-1c"))
                messagebox.showinfo("Info", f"{title} збережено", parent=win)
            except PermissionError as e:
                messagebox.showerror("Доступ заборонено", str(e), parent=win)

        ttk.Button(win, text="Зберегти", command=save).pack(pady=(0, 10))

    # ---------------------------------------------------------------------------------
    # Мандатне розмежування (lab2) — вікна працюють лише в режимі MAC
    # ---------------------------------------------------------------------------------
    def open_resources_dialog(self):
        try:
            labels = mac_sync_resources(mac_load_labels())
        except AccessModelError as e:
            messagebox.showerror("Error", str(e))
            return

        dialog = tk.Toplevel(self)
        dialog.title("Ресурси (мандатне розмежування)")
        dialog.geometry("520x300")
        dialog.grab_set()

        user_level = mac_get_user_level(self.db, self.current_user)
        ttk.Label(dialog, text=f"Ваш рівень доступу: {mac_level_name(user_level)}").pack(pady=(10, 0))

        tree = ttk.Treeview(dialog, columns=("label", "access"), height=8)
        tree.heading("#0", text="Ресурс")
        tree.heading("label", text="Мітка")
        tree.heading("access", text="Доступ")
        tree.column("#0", width=160)
        tree.column("label", width=170)
        tree.column("access", width=140)
        for name in sorted(labels):
            access = "повний" if mac_check_access(self.db, labels, self.current_user, name) else "заборонено"
            tree.insert("", "end", iid=name, text=name, values=(mac_level_name(labels[name]), access))
        tree.pack(padx=10, pady=10, fill="both", expand=True)

        def open_selected():
            if not tree.selection():
                return
            name = tree.selection()[0]
            try:
                if name.endswith(EXECUTABLE_EXT):
                    res = mac_execute_resource(self.db, labels, self.current_user, name)
                    messagebox.showinfo(name, f"Код: {res.returncode}\n\n{res.stdout}{res.stderr}",
                                        parent=dialog)
                elif name.endswith(TEXT_EXT):
                    content = mac_read_resource(self.db, labels, self.current_user, name)
                    self._text_window(name, content, lambda c: mac_write_resource(
                        self.db, labels, self.current_user, name, c))
                else:
                    mac_open_image_resource(self.db, labels, self.current_user, name)
            except PermissionError as e:
                messagebox.showerror("Доступ заборонено", str(e), parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        ttk.Button(dialog, text="Відкрити", command=open_selected).pack(pady=(0, 10))

    def open_labels_dialog(self):
        try:
            labels = mac_sync_resources(mac_load_labels())
        except AccessModelError as e:
            messagebox.showerror("Error", str(e))
            return
        level_values = [mac_level_name(l) for l in ACCESS_LEVELS]

        dialog = tk.Toplevel(self)
        dialog.title("Мандатні мітки")
        dialog.geometry("420x330")
        dialog.grab_set()

        ttk.Label(dialog, text="Рівень доступу користувача", font=("Arial", 11, "bold")).pack(pady=(10, 0))
        user_select = ttk.Combobox(dialog, values=list(self.db.keys()), state="readonly", width=30)
        user_level_select = ttk.Combobox(dialog, values=level_values, state="readonly", width=30)
        user_select.bind("<<ComboboxSelected>>",
                         lambda e: user_level_select.current(mac_get_user_level(self.db, user_select.get())))
        user_select.pack(pady=3)
        user_level_select.pack(pady=3)

        def apply_user():
            if user_select.get() and user_level_select.get():
                mac_set_user_level(self.db, user_select.get(), user_level_select.current())
                messagebox.showinfo("Info", "Рівень користувача збережено", parent=dialog)

        ttk.Button(dialog, text="Зберегти рівень", command=apply_user).pack(pady=5)

        ttk.Label(dialog, text="Мітка конфіденційності ресурсу", font=("Arial", 11, "bold")).pack(pady=(10, 0))
        res_select = ttk.Combobox(dialog, values=sorted(labels), state="readonly", width=30)
        res_level_select = ttk.Combobox(dialog, values=level_values, state="readonly", width=30)
        res_select.bind("<<ComboboxSelected>>",
                        lambda e: res_level_select.current(mac_get_resource_label(labels, res_select.get())))
        res_select.pack(pady=3)
        res_level_select.pack(pady=3)

        def apply_resource():
            if res_select.get() and res_level_select.get():
                mac_set_resource_label(labels, res_select.get(), res_level_select.current())
                messagebox.showinfo("Info", "Мітку ресурсу збережено", parent=dialog)

        ttk.Button(dialog, text="Зберегти мітку", command=apply_resource).pack(pady=5)

    # ---------------------------------------------------------------------------------
    # Дискреційне розмежування — вікна працюють лише в режимі DAC
    # ---------------------------------------------------------------------------------
    def _dac_acl(self, parent=None):
        try:
            return dac_sync(dac_load_acl(), self.db)
        except AccessModelError as e:
            messagebox.showerror("Error", str(e), parent=parent)
            return None

    def open_dac_resources_dialog(self):
        acl = self._dac_acl()
        if acl is None:
            return
        user = self.current_user

        dialog = tk.Toplevel(self)
        dialog.title("Ресурси (дискреційне розмежування)")
        dialog.geometry("760x340")
        dialog.grab_set()

        ttk.Label(dialog, text=f"Ваші права доступу ({user}), зараз "
                               f"{WEEKDAYS[datetime.now().weekday()]} {datetime.now().strftime('%H:%M')}").pack(pady=(10, 0))

        tree = ttk.Treeview(dialog, columns=("owner", "rights", "restr", "now"), height=9)
        for col, title, width in (("#0", "Ресурс", 130), ("owner", "Власник", 100),
                                  ("rights", "Права", 220), ("restr", "Обмеження", 200),
                                  ("now", "Зараз", 90)):
            tree.heading(col, text=title)
            tree.column(col, width=width)
        for name in sorted(acl):
            entry = dac_get_entry(acl, user, name)
            if entry:
                rights = ", ".join(right_title(name, r) for r in entry["rights"])
                restr = restrictions_text(entry)
                active = "активні" if _entry_active(entry, datetime.now())[0] else "неактивні"
            else:
                rights, restr, active = "немає", "-", "-"
            tree.insert("", "end", iid=name, text=name,
                        values=(acl[name]["owner"], rights, restr, active))
        tree.pack(padx=10, pady=10, fill="both", expand=True)

        def run(action):
            if not tree.selection():
                return
            name = tree.selection()[0]
            try:
                action(name)
            except PermissionError as e:
                messagebox.showerror("Доступ заборонено", str(e), parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def view(name):
            if name.endswith(EXECUTABLE_EXT):
                raise PermissionError(f"Для {name} право перегляду не передбачене ")
            if name.endswith(TEXT_EXT):
                self._text_window(name, dac_read_resource(self.db, acl, user, name))
            else:
                dac_open_image(self.db, acl, user, name, edit=False)

        def edit(name):
            if name.endswith(TEXT_EXT + EXECUTABLE_EXT):
                content = dac_load_for_edit(self.db, acl, user, name)
                self._text_window(name, content,
                                  lambda c: dac_write_resource(self.db, acl, user, name, c))
            else:
                dac_open_image(self.db, acl, user, name, edit=True)

        def execute(name):
            if not name.endswith(EXECUTABLE_EXT):
                raise PermissionError(f"{name} не є виконуваним файлом")
            res = dac_execute_resource(self.db, acl, user, name)
            messagebox.showinfo(name, f"Код: {res.returncode}\n\n{res.stdout}{res.stderr}", parent=dialog)

        buttons = ttk.Frame(dialog)
        buttons.pack(pady=(0, 10))
        for text, action in (("Переглянути", view), ("Редагувати", edit), ("Виконати", execute)):
            ttk.Button(buttons, text=text, command=lambda a=action: run(a)).pack(side="left", padx=5)

    def open_dac_matrix_dialog(self):
        acl = self._dac_acl()
        if acl is None:
            return
        header, rows = dac_matrix_rows(self.db, acl)

        dialog = tk.Toplevel(self)
        dialog.title("Матриця доступу")
        dialog.geometry("980x460")
        dialog.grab_set()

        tree = ttk.Treeview(dialog, columns=header[1:], height=len(rows))
        tree.heading("#0", text=header[0])
        tree.column("#0", width=100)
        for col in header[1:]:
            tree.heading(col, text=col)
            tree.column(col, width=170)
        for row in rows:
            tree.insert("", "end", text=row[0], values=row[1:])
        tree.pack(padx=10, pady=(10, 5), fill="x")

        ttk.Label(dialog, text="r - перегляд, w - редагування/збереження, x - виконання, "
                               "O - власник").pack()

        lists = tk.Text(dialog, wrap="word", height=12)
        lists.insert("1.0", "Списки доступу (ACL):\n" + dac_acl_lists_text(acl))
        lists.configure(state="disabled")
        lists.pack(padx=10, pady=5, fill="both", expand=True)

    def open_dac_rights_dialog(self):
        acl = self._dac_acl()
        if acl is None:
            return
        actor = self.current_user
        managed = [r for r in sorted(acl) if dac_can_manage(self.db, acl, actor, r)]
        if not managed:
            messagebox.showerror("Error", "Ви не є власником жодного ресурсу")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Керування правами доступу")
        dialog.geometry("440x560")
        dialog.grab_set()

        ttk.Label(dialog, text="Ресурс:").pack(anchor="w", padx=20, pady=(10, 0))
        res_select = ttk.Combobox(dialog, values=managed, state="readonly", width=32)
        res_select.pack(padx=20, pady=3)
        owner_label = ttk.Label(dialog, text="Власник: -", foreground="gray")
        owner_label.pack(anchor="w", padx=20)

        ttk.Label(dialog, text="Користувач:").pack(anchor="w", padx=20, pady=(8, 0))
        user_select = ttk.Combobox(dialog, values=list(self.db), state="readonly", width=32)
        user_select.pack(padx=20, pady=3)

        ttk.Label(dialog, text="Права:", font=("Arial", 11, "bold")).pack(anchor="w", padx=20, pady=(8, 0))
        rights_frame = ttk.Frame(dialog)
        rights_frame.pack(anchor="w", padx=30)
        right_vars = {}

        ttk.Label(dialog, text="Час доступу (HH:MM), порожньо — без обмежень:").pack(anchor="w", padx=20, pady=(8, 0))
        time_frame = ttk.Frame(dialog)
        time_frame.pack(anchor="w", padx=30)
        ttk.Label(time_frame, text="з").pack(side="left")
        time_from = ttk.Entry(time_frame, width=7)
        time_from.pack(side="left", padx=5)
        ttk.Label(time_frame, text="до").pack(side="left")
        time_to = ttk.Entry(time_frame, width=7)
        time_to.pack(side="left", padx=5)

        ttk.Label(dialog, text="Дні тижня (жодного — без обмежень):").pack(anchor="w", padx=20, pady=(8, 0))
        days_frame = ttk.Frame(dialog)
        days_frame.pack(anchor="w", padx=30)
        day_vars = [tk.BooleanVar() for _ in WEEKDAYS]
        for i, d in enumerate(WEEKDAYS):
            ttk.Checkbutton(days_frame, text=d, variable=day_vars[i]).pack(side="left")

        ttk.Label(dialog, text="Діє до (YYYY-MM-DD), порожньо — безстроково:").pack(anchor="w", padx=20, pady=(8, 0))
        expires_entry = ttk.Entry(dialog, width=14)
        expires_entry.pack(anchor="w", padx=30)

        def set_entry(widget, value):
            widget.delete(0, "end")
            widget.insert(0, value or "")

        def refresh(*_):
            res = res_select.get()
            if not res:
                return
            owner_label.config(text=f"Власник: {acl[res]['owner']}")
            for w in rights_frame.winfo_children():
                w.destroy()
            right_vars.clear()
            for r in rights_for_type(res):
                right_vars[r] = tk.BooleanVar()
                ttk.Checkbutton(rights_frame, text=f"{r} — {right_title(res, r)}",
                                variable=right_vars[r]).pack(anchor="w")
            entry = acl[res]["acl"].get(user_select.get()) or {}
            for r, var in right_vars.items():
                var.set(r in entry.get("rights", ""))
            time = entry.get("time") or ("", "")
            set_entry(time_from, time[0])
            set_entry(time_to, time[1])
            for i, var in enumerate(day_vars):
                var.set(i in (entry.get("days") or []))
            set_entry(expires_entry, entry.get("expires"))

        res_select.bind("<<ComboboxSelected>>", refresh)
        user_select.bind("<<ComboboxSelected>>", refresh)

        def action(func):
            res, user = res_select.get(), user_select.get()
            if not res or not user:
                messagebox.showerror("Error", "Оберіть ресурс та користувача", parent=dialog)
                return
            try:
                msg = func(res, user)
                messagebox.showinfo("Info", msg, parent=dialog)
                refresh()
            except (PermissionError, ValueError, KeyError) as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def grant(res, user):
            t_from, t_to = time_from.get().strip(), time_to.get().strip()
            if bool(t_from) != bool(t_to):
                raise ValueError("Вкажіть початок та кінець часового вікна")
            rights = "".join(r for r, v in right_vars.items() if v.get())
            days = [i for i, v in enumerate(day_vars) if v.get()]
            dac_grant(self.db, acl, actor, user, res, rights,
                      (t_from, t_to) if t_from else None, days or None,
                      expires_entry.get().strip() or None)
            return f"Права {user} на {res} збережено" if rights else f"Права {user} на {res} відкликано"

        def revoke(res, user):
            dac_revoke(self.db, acl, actor, user, res)
            return f"Усі права {user} на {res} відкликано"

        def owner(res, user):
            if not messagebox.askyesno("Підтвердження", f"Передати власність на {res} користувачу {user}?",
                                       parent=dialog):
                return "Скасовано"
            dac_set_owner(self.db, acl, actor, user, res)
            return f"Готово!"

        buttons = ttk.Frame(dialog)
        buttons.pack(pady=15)
        ttk.Button(buttons, text="Надати / змінити", command=lambda: action(grant)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Відкликати", command=lambda: action(revoke)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Зробити власником", command=lambda: action(owner)).pack(side="left", padx=4)

        res_select.current(0)
        refresh()


def print_matrix():
    if get_access_model() != DISCRETIONARY:
        print(f"Поточна модель: {ACCESS_MODELS[get_access_model()]}. "
              f"Матриця доступу доступна лише при дискреційному розмежуванні.")
        return
    db = load_db()
    acl = dac_sync(dac_load_acl(), db)
    print("Матриця доступу:")
    print(dac_matrix_text(db, acl))
    print("\nСписки доступу (ACL):")
    print(dac_acl_lists_text(acl))


if __name__ == "__main__":
    init_settings()
    model = get_access_model()
    if model == MANDATORY:
        mac_load_labels()      # при першому запуску налаштовує політику MAC
    elif model == DISCRETIONARY:
        dac_sync(dac_load_acl(), load_db())
    app = App()
    app.mainloop()
