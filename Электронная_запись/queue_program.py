#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПРОГРАММА УПРАВЛЕНИЯ ЭЛЕКТРОННОЙ ОЧЕРЕДЬЮ
АСИНХРОННАЯ ВЕРСИЯ - БЕЗ ЗАВИСАНИЙ
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta
import threading
import time
import re
import os
from concurrent.futures import ThreadPoolExecutor
from queue import Queue as ThreadQueue

# TTS опционально
try:
    import pyttsx3
    import winsound

    TTS_ENGINE = pyttsx3.init()
    TTS_ENGINE.setProperty('rate', 150)
    TTS_ENGINE.setProperty('volume', 1.0)
    HAS_TTS = True
except:
    print("TTS не доступен")
    TTS_ENGINE = None
    HAS_TTS = False

CHECK_INTERVAL = 10

# ------------------------------
# Темы оформления (Light/Dark)
# ------------------------------
THEMES = {
    "light": {
        "bg": "#F5F7FA",
        "card": "#FFFFFF",
        "text": "#111827",
        "muted": "#6B7280",
        "primary": "#1E88E5",
        "border": "#E5E7EB",
        "tree_bg": "#FFFFFF",
        "tree_fg": "#111827",
        "tree_sel_bg": "#DBEAFE",
        "tree_sel_fg": "#111827",
        "btn_bg": "#1E88E5",
        "btn_fg": "#FFFFFF",
        "danger_bg": "#E53935",
        "danger_fg": "#FFFFFF",
        "warn_bg": "#FB8C00",
        "warn_fg": "#FFFFFF",
        "ok_bg": "#43A047",
        "ok_fg": "#FFFFFF",
    },
    "dark": {
        "bg": "#0F172A",
        "card": "#111827",
        "text": "#E5E7EB",
        "muted": "#9CA3AF",
        "primary": "#60A5FA",
        "border": "#1F2937",
        "tree_bg": "#111827",
        "tree_fg": "#E5E7EB",
        "tree_sel_bg": "#1D4ED8",
        "tree_sel_fg": "#FFFFFF",
        "btn_bg": "#2563EB",
        "btn_fg": "#FFFFFF",
        "danger_bg": "#EF4444",
        "danger_fg": "#FFFFFF",
        "warn_bg": "#F59E0B",
        "warn_fg": "#111827",
        "ok_bg": "#22C55E",
        "ok_fg": "#0B1220",
    },
}


def _safe_config(widget, **kwargs):
    try:
        widget.configure(**kwargs)
    except Exception:
        pass


class ThemeManager:
    def __init__(self, root: tk.Tk, initial: str = "light"):
        self.root = root
        self.name = initial if initial in THEMES else "light"
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self.apply()

    @property
    def t(self):
        return THEMES[self.name]

    def toggle(self):
        self.name = "dark" if self.name == "light" else "light"
        self.apply()

    def apply(self):
        t = self.t
        _safe_config(self.root, bg=t["bg"])

        # ttk styles
        self.style.configure("TFrame", background=t["bg"])
        self.style.configure("Card.TFrame", background=t["card"])
        self.style.configure("TLabel", background=t["bg"], foreground=t["text"])
        self.style.configure("Card.TLabel", background=t["card"], foreground=t["text"])
        self.style.configure("Muted.TLabel", background=t["card"], foreground=t["muted"])
        self.style.configure("TLabelframe", background=t["card"], foreground=t["text"])
        self.style.configure("TLabelframe.Label", background=t["card"], foreground=t["text"])

        self.style.configure("Primary.TButton", background=t["btn_bg"], foreground=t["btn_fg"], padding=10)
        self.style.map("Primary.TButton",
                       background=[("active", t["primary"]), ("pressed", t["primary"])],
                       foreground=[("disabled", t["muted"])])

        self.style.configure("Ok.TButton", background=t["ok_bg"], foreground=t["ok_fg"], padding=10)
        self.style.configure("Warn.TButton", background=t["warn_bg"], foreground=t["warn_fg"], padding=10)
        self.style.configure("Danger.TButton", background=t["danger_bg"], foreground=t["danger_fg"], padding=10)

        # Treeview
        self.style.configure("Treeview",
                             background=t["tree_bg"],
                             foreground=t["tree_fg"],
                             fieldbackground=t["tree_bg"],
                             bordercolor=t["border"],
                             rowheight=28)
        self.style.configure("Treeview.Heading",
                             background=t["card"],
                             foreground=t["text"],
                             relief="flat")
        self.style.map("Treeview",
                       background=[("selected", t["tree_sel_bg"])],
                       foreground=[("selected", t["tree_sel_fg"])])


def apply_theme_recursive(widget, theme: dict):
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        _safe_config(widget, bg=theme["bg"])
    if isinstance(widget, tk.Frame):
        try:
            current = str(widget.cget("bg")).lower()
        except Exception:
            current = ""
        if current in ("#1976d2", "rgb(25,118,210)", "#2196f3"):
            _safe_config(widget, bg=theme["primary"])
        else:
            _safe_config(widget, bg=theme["bg"])
    if isinstance(widget, tk.LabelFrame):
        _safe_config(widget, bg=theme["card"], fg=theme["text"])
    if isinstance(widget, tk.Label):
        bg = widget.cget("bg")
        new_bg = theme["card"] if bg.lower() in ("white", "#ffffff") else theme["bg"]
        _safe_config(widget, bg=new_bg, fg=theme["text"])
    if isinstance(widget, tk.Button):
        try:
            current = str(widget.cget("bg")).lower()
        except Exception:
            current = ""
        if current in (
                "systembuttonface", "#f0f0f0", "white", "#ffffff", theme["bg"].lower(), theme["card"].lower(), ""):
            _safe_config(widget, bg=theme["btn_bg"], fg=theme["btn_fg"], activebackground=theme["primary"])
    for child in widget.winfo_children():
        apply_theme_recursive(child, theme)


class Database:
    """Асинхронный API клиент"""

    def __init__(self):
        self.api_base = os.getenv("API_BASE", "").strip().rstrip("/")
        if not self.api_base:
            self.api_base = "https://spatial-jaime-dental-clinictj-7c05d6e5.koyeb.app"

        try:
            import requests
            self._requests = requests
        except Exception as e:
            raise RuntimeError("Не установлен пакет requests. Установите: pip install requests") from e

        # Thread pool для асинхронных запросов
        self.executor = ThreadPoolExecutor(max_workers=5)

        # Проверка доступности
        try:
            self.api_get("/api/health", timeout=6)
            print(f"✓ Подключено к API: {self.api_base}")
        except Exception as e:
            print(f"⚠ Не удалось подключиться к API: {e}")

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.api_base}{path}"

    def api_get(self, path: str, params: dict = None, timeout: int = 20):
        """GET запрос к API"""
        try:
            r = self._requests.get(self._url(path), params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"API GET error [{path}]: {e}")
            raise

    def api_post(self, path: str, payload: dict = None, timeout: int = 20):
        """POST запрос к API"""
        try:
            r = self._requests.post(self._url(path), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"API POST error [{path}]: {e}")
            raise

    def api_put(self, path: str, payload: dict = None, timeout: int = 20):
        """PUT запрос к API"""
        try:
            r = self._requests.put(self._url(path), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"API PUT error [{path}]: {e}")
            raise

    # ---------- Асинхронные методы ----------
    def get_doctors_async(self, callback):
        """Асинхронное получение врачей"""

        def task():
            try:
                data = self.api_get("/api/doctors")
                result = data if isinstance(data, list) else []
                callback(result, None)
            except Exception as e:
                callback([], str(e))

        self.executor.submit(task)

    def get_queue_async(self, callback):
        """Асинхронное получение очереди"""

        def task():
            try:
                data = self.api_get("/api/queue")
                result = data if isinstance(data, list) else []
                callback(result, None)
            except Exception as e:
                callback([], str(e))

        self.executor.submit(task)

    def get_appointments_async(self, date_str, callback):
        """Асинхронное получение записей"""

        def task():
            try:
                params = {"date": date_str}
                data = self.api_get("/api/appointments/today", params=params)
                result = data if isinstance(data, list) else []
                callback(result, None)
            except Exception as e:
                callback([], str(e))

        self.executor.submit(task)

    def get_stats_async(self, callback):
        """Асинхронное получение статистики"""

        def task():
            try:
                data = self.api_get("/api/stats")
                result = data if isinstance(data, dict) else {
                    'total': 0, 'active': 0, 'cancelled': 0, 'completed': 0, 'doctors': []
                }
                callback(result, None)
            except Exception as e:
                callback({'total': 0, 'active': 0, 'cancelled': 0, 'completed': 0, 'doctors': []}, str(e))

        self.executor.submit(task)

    # ---------- Синхронные методы для простых операций ----------
    def get_doctors(self):
        """GET /api/doctors"""
        try:
            data = self.api_get("/api/doctors")
            return data if isinstance(data, list) else []
        except:
            return []

    def update_doctor_status(self, doctor_id: int, new_status: str):
        """PUT /api/doctors/{doctor_id}/status"""
        try:
            payload = {"status": new_status}
            return self.api_put(f"/api/doctors/{doctor_id}/status", payload)
        except Exception as e:
            raise Exception(f"Не удалось обновить статус врача: {e}")

    def get_available_slots(self, date_str: str, doctor_id: int = None):
        """GET /api/available-slots

        Возвращает список строк времени (['08:00', '08:30', ...]).
        Если API недоступен/медленный, возвращаем дефолтные слоты,
        чтобы UI не оставался пустым (и пользователь мог выбрать время).
        """

        def _default_slots():
            # 08:00–18:00 каждые 30 минут
            out = []
            h, m = 8, 0
            while True:
                out.append(f"{h:02d}:{m:02d}")
                m += 30
                if m >= 60:
                    h += 1
                    m -= 60
                if h > 18 or (h == 18 and m > 0):
                    break
            return out

        try:
            params = {"date": date_str}
            if doctor_id:
                params["doctor_id"] = doctor_id
            data = self.api_get("/api/available-slots", params=params)

            # Нормализация ответа
            slots = []
            if isinstance(data, list):
                if data and isinstance(data[0], str):
                    slots = data
                elif data and isinstance(data[0], dict):
                    for item in data:
                        t = item.get("time") or item.get("slot") or item.get("appointment_time")
                        if t and item.get("available", True):
                            slots.append(str(t))
                else:
                    slots = []
            else:
                slots = []

            # Если сервер вернул пусто — лучше показать дефолт, чем «пустое поле»
            if not slots:
                return _default_slots()

            # unique preserve order
            seen = set()
            norm = []
            for t in slots:
                if t not in seen:
                    seen.add(t)
                    norm.append(t)
            return norm
        except Exception as e:
            print(f"API GET error [/api/available-slots]: {e}")
            return _default_slots()

    def create_appointment(self, patient_name: str, phone: str, doctor_id: int,
                           appointment_date: str, appointment_time: str, service_id: int = None):
        """POST /api/appointments"""
        try:
            payload = {
                "patient_name": patient_name,
                "phone": phone,
                "doctor_id": doctor_id,
                "appointment_date": appointment_date,
                "appointment_time": appointment_time
            }
            if service_id:
                payload["service_id"] = service_id

            return self.api_post("/api/appointments", payload)
        except Exception as e:
            raise Exception(f"Не удалось создать запись: {e}")

    def update_appointment(self, apt_id: int, doctor_id: int = None,
                           appointment_time: str = None, appointment_date: str = None):
        """Обновление записи (предполагается endpoint PUT /api/appointments/{apt_id})"""
        try:
            payload = {}
            if doctor_id is not None:
                payload["doctor_id"] = doctor_id
            if appointment_time:
                payload["appointment_time"] = appointment_time
            if appointment_date:
                payload["appointment_date"] = appointment_date

            return self.api_put(f"/api/appointments/{apt_id}", payload)
        except Exception as e:
            raise Exception(f"Не удалось обновить запись: {e}")

    def cancel_appointment(self, apt_id: int):
        """PUT /api/appointments/{apt_id}/cancel"""
        try:
            return self.api_put(f"/api/appointments/{apt_id}/cancel")
        except Exception as e:
            raise Exception(f"Не удалось отменить запись: {e}")

    def get_queue(self):
        """GET /api/queue"""
        try:
            data = self.api_get("/api/queue")
            return data if isinstance(data, list) else []
        except:
            return []

    def add_to_queue(self, appointment_id: int):
        """Добавление записи в очередь (POST /api/queue)"""
        try:
            payload = {"appointment_id": appointment_id}
            return self.api_post("/api/queue", payload)
        except Exception as e:
            raise Exception(f"Не удалось добавить в очередь: {e}")

    def update_queue_status(self, queue_id: int, new_status: str):
        """Обновление статуса в очереди"""
        try:
            payload = {"status": new_status}
            return self.api_put(f"/api/queue/{queue_id}/status", payload)
        except Exception as e:
            print(f"Не удалось обновить статус очереди: {e}")
            raise

    def search_appointments(self, patient_name: str):
        """Поиск записей по имени пациента"""
        try:
            params = {"patient_name": patient_name}
            data = self.api_get("/api/appointments/search", params=params)
            return data if isinstance(data, list) else []
        except:
            # Если нет специального endpoint, ищем вручную
            all_appointments = []
            for days in range(-30, 30):  # Ищем в диапазоне ±30 дней
                date = (datetime.now().date() + timedelta(days=days)).strftime("%Y-%m-%d")
                try:
                    apts = self.api_get("/api/appointments/today", params={"date": date})
                    if isinstance(apts, list):
                        all_appointments.extend(apts)
                except:
                    pass

            # Фильтруем по имени
            patient_name_lower = patient_name.lower()
            return [apt for apt in all_appointments
                    if patient_name_lower in apt.get('patient_name', '').lower()]


class AdminPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Панель управления - Электронная очередь")
        self.root.geometry("1400x900")

        self.db = Database()
        self.theme_manager = ThemeManager(root, "light")
        self.patient_display = None
        self.current_date = datetime.now().date()

        # Для асинхронных обновлений
        self.ui_queue = ThreadQueue()
        self.is_refreshing = False

        self.create_ui()
        self.start_ui_queue_processor()
        self.refresh_all()
        self.start_auto_refresh()

    def create_ui(self):
        # Верхняя панель
        top_panel = ttk.Frame(self.root, style="TFrame")
        top_panel.pack(fill='x', padx=10, pady=10)

        ttk.Label(top_panel, text="ПАНЕЛЬ УПРАВЛЕНИЯ",
                  font=('Arial', 20, 'bold'), style="TLabel").pack(side='left')

        btn_frame = ttk.Frame(top_panel, style="TFrame")
        btn_frame.pack(side='right')

        ttk.Button(btn_frame, text="🌓 Тема", command=self.toggle_theme,
                   style="Primary.TButton", width=10).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📊 Статистика", command=self.show_statistics,
                   style="Primary.TButton", width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📺 Экран очереди", command=self.open_patient_display,
                   style="Ok.TButton", width=15).pack(side='left', padx=5)

        # Главный контейнер
        main_container = ttk.Frame(self.root, style="TFrame")
        main_container.pack(fill='both', expand=True, padx=10, pady=10)

        # Левая колонка - Врачи и Очередь
        left_column = ttk.Frame(main_container, style="TFrame")
        left_column.pack(side='left', fill='both', expand=True, padx=(0, 5))

        # Врачи
        doctors_frame = ttk.LabelFrame(left_column, text="Врачи", style="TLabelframe")
        doctors_frame.pack(fill='both', expand=True, pady=(0, 10))

        self.doctors_tree = ttk.Treeview(doctors_frame, columns=('name', 'room', 'status'),
                                         show='headings', height=6)
        self.doctors_tree.heading('name', text='Врач')
        self.doctors_tree.heading('room', text='Кабинет')
        self.doctors_tree.heading('status', text='Статус')
        self.doctors_tree.column('name', width=200)
        self.doctors_tree.column('room', width=100)
        self.doctors_tree.column('status', width=100)
        self.doctors_tree.pack(fill='both', expand=True, padx=5, pady=5)

        doctors_btn_frame = ttk.Frame(doctors_frame, style="TFrame")
        doctors_btn_frame.pack(fill='x', padx=5, pady=5)

        ttk.Button(doctors_btn_frame, text="Свободен", command=self.set_doctor_free,
                   style="Ok.TButton", width=12).pack(side='left', padx=2)
        ttk.Button(doctors_btn_frame, text="Выходной", command=self.set_doctor_dayoff,
                   style="Warn.TButton", width=12).pack(side='left', padx=2)
        ttk.Button(doctors_btn_frame, text="Перерыв", command=self.set_doctor_break,
                   style="Danger.TButton", width=12).pack(side='left', padx=2)

        # Очередь
        queue_frame = ttk.LabelFrame(left_column, text="Текущая очередь", style="TLabelframe")
        queue_frame.pack(fill='both', expand=True)

        self.queue_tree = ttk.Treeview(queue_frame,
                                       columns=('patient', 'service', 'doctor', 'room', 'status'),
                                       show='headings', height=8)
        self.queue_tree.heading('patient', text='Пациент')
        self.queue_tree.heading('service', text='Услуга')
        self.queue_tree.heading('doctor', text='Врач')
        self.queue_tree.heading('room', text='Кабинет')
        self.queue_tree.heading('status', text='Статус')
        self.queue_tree.column('patient', width=150)
        self.queue_tree.column('service', width=100)
        self.queue_tree.column('doctor', width=120)
        self.queue_tree.column('room', width=80)
        self.queue_tree.column('status', width=100)
        self.queue_tree.pack(fill='both', expand=True, padx=5, pady=5)

        queue_btn_frame = ttk.Frame(queue_frame, style="TFrame")
        queue_btn_frame.pack(fill='x', padx=5, pady=5)

        ttk.Button(queue_btn_frame, text="Пригласить", command=self.call_patient,
                   style="Ok.TButton", width=15).pack(side='left', padx=2)
        ttk.Button(queue_btn_frame, text="Принять", command=self.accept_patient,
                   style="Primary.TButton", width=15).pack(side='left', padx=2)
        ttk.Button(queue_btn_frame, text="Завершить", command=self.complete_patient,
                   style="Warn.TButton", width=15).pack(side='left', padx=2)

        # Правая колонка - Записи
        right_column = ttk.Frame(main_container, style="TFrame")
        right_column.pack(side='right', fill='both', expand=True, padx=(5, 0))

        appointments_frame = ttk.LabelFrame(right_column, text="Записи на приём", style="TLabelframe")
        appointments_frame.pack(fill='both', expand=True)

        # Календарь
        date_frame = ttk.Frame(appointments_frame, style="TFrame")
        date_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(date_frame, text="Дата:", style="TLabel").pack(side='left', padx=5)

        self.date_label = ttk.Label(date_frame, text=self.current_date.strftime("%d.%m.%Y"),
                                    style="TLabel", font=('Arial', 11, 'bold'))
        self.date_label.pack(side='left', padx=5)

        ttk.Button(date_frame, text="◀", command=self.prev_day, width=3).pack(side='left', padx=2)
        ttk.Button(date_frame, text="Сегодня", command=self.today, width=10).pack(side='left', padx=2)
        ttk.Button(date_frame, text="▶", command=self.next_day, width=3).pack(side='left', padx=2)

        # Таблица записей
        self.appointments_tree = ttk.Treeview(appointments_frame,
                                              columns=('time', 'patient', 'phone', 'service', 'doctor'),
                                              show='headings', height=20)
        self.appointments_tree.heading('time', text='Время')
        self.appointments_tree.heading('patient', text='Пациент')
        self.appointments_tree.heading('phone', text='Телефон')
        self.appointments_tree.heading('service', text='Услуга')
        self.appointments_tree.heading('doctor', text='Врач')
        self.appointments_tree.column('time', width=80)
        self.appointments_tree.column('patient', width=150)
        self.appointments_tree.column('phone', width=120)
        self.appointments_tree.column('service', width=100)
        self.appointments_tree.column('doctor', width=120)
        self.appointments_tree.pack(fill='both', expand=True, padx=5, pady=5)

        # Кнопки записей
        apt_btn_frame = ttk.Frame(appointments_frame, style="TFrame")
        apt_btn_frame.pack(fill='x', padx=5, pady=5)

        ttk.Button(apt_btn_frame, text="+ Новая запись", command=self.create_appointment,
                   style="Ok.TButton", width=15).pack(side='left', padx=2)
        ttk.Button(apt_btn_frame, text="✏️ Изменить", command=self.edit_appointment,
                   style="Primary.TButton", width=15).pack(side='left', padx=2)
        ttk.Button(apt_btn_frame, text="📞 Пригласить", command=self.invite_from_appointment,
                   style="Warn.TButton", width=15).pack(side='left', padx=2)
        ttk.Button(apt_btn_frame, text="🔍 Отменить", command=self.cancel_appointment_with_search,
                   style="Danger.TButton", width=15).pack(side='left', padx=2)
        ttk.Button(apt_btn_frame, text="🔄 Обновить", command=self.refresh_all,
                   style="Primary.TButton", width=15).pack(side='left', padx=2)

    def start_ui_queue_processor(self):
        """Обработчик очереди UI-обновлений"""

        def process_queue():
            try:
                while True:
                    task = self.ui_queue.get(timeout=0.1)
                    if task:
                        task()
            except:
                pass
            self.root.after(100, process_queue)

        process_queue()

    def toggle_theme(self):
        self.theme_manager.toggle()
        apply_theme_recursive(self.root, self.theme_manager.t)
        if self.patient_display and self.patient_display.winfo_exists():
            apply_theme_recursive(self.patient_display, self.theme_manager.t)

    # ---------- Управление датой ----------
    def prev_day(self):
        self.current_date -= timedelta(days=1)
        self.date_label.config(text=self.current_date.strftime("%d.%m.%Y"))
        self.refresh_appointments()

    def today(self):
        self.current_date = datetime.now().date()
        self.date_label.config(text=self.current_date.strftime("%d.%m.%Y"))
        self.refresh_appointments()

    def next_day(self):
        self.current_date += timedelta(days=1)
        self.date_label.config(text=self.current_date.strftime("%d.%m.%Y"))
        self.refresh_appointments()

    # ---------- Управление врачами ----------
    def set_doctor_free(self):
        self._change_doctor_status('свободен', 'свободен')

    def set_doctor_dayoff(self):
        self._change_doctor_status('выходной', 'выходной')

    def set_doctor_break(self):
        self._change_doctor_status('перерыв', 'на перерыве')

    def _change_doctor_status(self, status, message_status):
        selected = self.doctors_tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите врача")
            return

        item = self.doctors_tree.item(selected[0])
        doctor_name = item['values'][0]

        def task():
            try:
                doctors = self.db.get_doctors()
                doctor = next((d for d in doctors if d['name'] == doctor_name), None)
                if doctor:
                    self.db.update_doctor_status(doctor['id'], status)
                    self.ui_queue.put(lambda: self.refresh_doctors())
                    self.ui_queue.put(
                        lambda: messagebox.showinfo("Успех", f"Врач {doctor_name} теперь {message_status}"))
            except Exception as e:
                self.ui_queue.put(lambda: messagebox.showerror("Ошибка", str(e)))

        threading.Thread(target=task, daemon=True).start()

    # ---------- Управление очередью ----------
    def call_patient(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите пациента из очереди")
            return

        queue_id = selected[0]
        item = self.queue_tree.item(queue_id)
        patient_name = item['values'][0]
        room = item['values'][3]

        def task():
            try:
                self.db.update_queue_status(int(queue_id), 'готов')
                self.ui_queue.put(lambda: self.announce_patient(patient_name, room))
                self.ui_queue.put(lambda: self.refresh_queue())
                if self.patient_display and self.patient_display.winfo_exists():
                    self.ui_queue.put(lambda: self.patient_display.refresh())
            except Exception as e:
                self.ui_queue.put(lambda: messagebox.showerror("Ошибка", f"Не удалось пригласить пациента: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def accept_patient(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите пациента из очереди")
            return

        queue_id = selected[0]
        item = self.queue_tree.item(queue_id)
        patient_name = item['values'][0]

        def task():
            try:
                self.db.update_queue_status(int(queue_id), 'в_работе')
                self.ui_queue.put(lambda: self.refresh_queue())
                self.ui_queue.put(lambda: messagebox.showinfo("Успех", f"Пациент {patient_name} принят"))
                if self.patient_display and self.patient_display.winfo_exists():
                    self.ui_queue.put(lambda: self.patient_display.refresh())
            except Exception as e:
                self.ui_queue.put(lambda: messagebox.showerror("Ошибка", f"Не удалось принять пациента: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def complete_patient(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите пациента из очереди")
            return

        queue_id = selected[0]
        item = self.queue_tree.item(queue_id)
        patient_name = item['values'][0]

        if messagebox.askyesno("Подтверждение", f"Завершить приём пациента {patient_name}?"):
            def task():
                try:
                    self.db.update_queue_status(int(queue_id), 'завершён')
                    self.ui_queue.put(lambda: self.refresh_queue())
                    self.ui_queue.put(lambda: messagebox.showinfo("Успех", f"Приём пациента {patient_name} завершён"))
                    if self.patient_display and self.patient_display.winfo_exists():
                        self.ui_queue.put(lambda: self.patient_display.refresh())
                except Exception as e:
                    self.ui_queue.put(lambda: messagebox.showerror("Ошибка", f"Не удалось завершить приём: {e}"))

            threading.Thread(target=task, daemon=True).start()

    # ---------- Управление записями ----------
    def create_appointment(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Новая запись")
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="НОВАЯ ЗАПИСЬ НА ПРИЁМ",
                  font=('Arial', 16, 'bold')).pack(pady=20)

        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=30, pady=10)

        # Имя пациента
        ttk.Label(form_frame, text="Имя пациента:").grid(row=0, column=0, sticky='w', pady=10)
        name_entry = ttk.Entry(form_frame, width=30)
        name_entry.grid(row=0, column=1, pady=10, padx=10)

        # Телефон
        ttk.Label(form_frame, text="Телефон:").grid(row=1, column=0, sticky='w', pady=10)
        phone_entry = ttk.Entry(form_frame, width=30)
        phone_entry.grid(row=1, column=1, pady=10, padx=10)

        # Дата
        ttk.Label(form_frame, text="Дата:").grid(row=2, column=0, sticky='w', pady=10)
        date_entry = ttk.Entry(form_frame, width=30)
        date_entry.insert(0, self.current_date.strftime("%Y-%m-%d"))
        date_entry.grid(row=2, column=1, pady=10, padx=10)

        # Врач
        ttk.Label(form_frame, text="Врач:").grid(row=3, column=0, sticky='w', pady=10)
        doctor_var = tk.StringVar()
        doctors = self.db.get_doctors()
        doctor_combo = ttk.Combobox(form_frame, textvariable=doctor_var, width=28, state='readonly')
        doctor_combo['values'] = [f"{d['name']} ({d['room']})" for d in doctors]
        if doctors:
            doctor_combo.current(0)
        doctor_combo.grid(row=3, column=1, pady=10, padx=10)

        # Время
        ttk.Label(form_frame, text="Время:").grid(row=4, column=0, sticky='w', pady=10)
        time_var = tk.StringVar()
        time_combo = ttk.Combobox(form_frame, textvariable=time_var, width=28, state='readonly')
        time_combo.grid(row=4, column=1, pady=10, padx=10)

        def update_time_slots(*args):
            selected = doctor_var.get()
            if not selected:
                return

            doctor_name = selected.split(' (')[0]
            doctor = next((d for d in doctors if d['name'] == doctor_name), None)
            if not doctor:
                return

            date_str = date_entry.get()

            def task():
                slots = self.db.get_available_slots(date_str, doctor['id'])
                self.ui_queue.put(lambda: time_combo.configure(values=slots))
                if slots:
                    self.ui_queue.put(lambda: time_combo.current(0))

            threading.Thread(target=task, daemon=True).start()

        doctor_combo.bind('<<ComboboxSelected>>', update_time_slots)
        date_entry.bind('<FocusOut>', update_time_slots)
        update_time_slots()

        # Кнопки
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side='bottom', fill='x', pady=10)

        def save_appointment():
            name = name_entry.get().strip()
            phone = phone_entry.get().strip()
            date_str = date_entry.get().strip()
            time_str = time_var.get().strip()
            selected_doctor = doctor_var.get()

            if not all([name, phone, date_str, time_str, selected_doctor]):
                messagebox.showwarning("Предупреждение", "Заполните все поля")
                return

            if not re.match(r'^\+?\d{9,15}$', phone.replace(' ', '').replace('-', '')):
                messagebox.showwarning("Предупреждение", "Неверный формат телефона")
                return

            doctor_name = selected_doctor.split(' (')[0]
            doctor = next((d for d in doctors if d['name'] == doctor_name), None)
            if not doctor:
                messagebox.showerror("Ошибка", "Врач не найден")
                return

            def task():
                try:
                    self.db.create_appointment(
                        patient_name=name,
                        phone=phone,
                        doctor_id=doctor['id'],
                        appointment_date=date_str,
                        appointment_time=time_str
                    )
                    self.ui_queue.put(lambda: messagebox.showinfo("Успех", "Запись успешно создана!"))
                    self.ui_queue.put(dialog.destroy)
                    self.ui_queue.put(lambda: self.refresh_appointments())
                except Exception as e:
                    self.ui_queue.put(lambda: messagebox.showerror("Ошибка", str(e)))

            threading.Thread(target=task, daemon=True).start()

        ttk.Button(btn_frame, text="Сохранить", command=save_appointment,
                   style="Ok.TButton", width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Danger.TButton", width=15).pack(side='left', padx=5)

    def edit_appointment(self):
        """Изменение записи (время и врач)"""
        selected = self.appointments_tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите запись для изменения")
            return

        apt_id = int(selected[0])
        item = self.appointments_tree.item(selected[0])
        current_time = item['values'][0]
        current_patient = item['values'][1]
        current_phone = item['values'][2]
        current_doctor = item['values'][4]

        dialog = tk.Toplevel(self.root)
        dialog.title("Изменить запись")
        dialog.geometry("500x500")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"ИЗМЕНЕНИЕ ЗАПИСИ",
                  font=('Arial', 16, 'bold')).pack(pady=20)

        ttk.Label(dialog, text=f"Пациент: {current_patient}",
                  font=('Arial', 12)).pack(pady=5)
        ttk.Label(dialog, text=f"Телефон: {current_phone}",
                  font=('Arial', 12)).pack(pady=5)

        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=30, pady=10)

        # Дата
        ttk.Label(form_frame, text="Дата:").grid(row=0, column=0, sticky='w', pady=10)
        date_entry = ttk.Entry(form_frame, width=30)
        date_entry.insert(0, self.current_date.strftime("%Y-%m-%d"))
        date_entry.grid(row=0, column=1, pady=10, padx=10)

        # Врач
        ttk.Label(form_frame, text="Врач:").grid(row=1, column=0, sticky='w', pady=10)
        doctor_var = tk.StringVar()
        doctors = self.db.get_doctors()
        doctor_combo = ttk.Combobox(form_frame, textvariable=doctor_var, width=28, state='readonly')
        doctor_combo['values'] = [f"{d['name']} ({d['room']})" for d in doctors]

        # Устанавливаем текущего врача
        for i, d in enumerate(doctors):
            if d['name'] == current_doctor:
                doctor_combo.current(i)
                break

        doctor_combo.grid(row=1, column=1, pady=10, padx=10)

        # Время
        ttk.Label(form_frame, text="Время:").grid(row=2, column=0, sticky='w', pady=10)
        time_var = tk.StringVar()
        time_combo = ttk.Combobox(form_frame, textvariable=time_var, width=28, state='readonly')
        time_combo.grid(row=2, column=1, pady=10, padx=10)

        def update_time_slots(*args):
            selected_doctor = doctor_var.get()
            if not selected_doctor:
                return

            doctor_name = selected_doctor.split(' (')[0]
            doctor = next((d for d in doctors if d['name'] == doctor_name), None)
            if not doctor:
                return

            date_str = date_entry.get()

            def task():
                slots = self.db.get_available_slots(date_str, doctor['id'])
                # Добавляем текущее время в список
                if current_time not in slots:
                    slots.insert(0, current_time)
                self.ui_queue.put(lambda: time_combo.configure(values=slots))
                self.ui_queue.put(lambda: time_var.set(current_time))

            threading.Thread(target=task, daemon=True).start()

        doctor_combo.bind('<<ComboboxSelected>>', update_time_slots)
        date_entry.bind('<FocusOut>', update_time_slots)
        update_time_slots()

        # Кнопки
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side='bottom', fill='x', pady=10)

        def save_changes():
            selected_doctor = doctor_var.get()
            new_time = time_var.get().strip()
            new_date = date_entry.get().strip()

            if not all([selected_doctor, new_time, new_date]):
                messagebox.showwarning("Предупреждение", "Заполните все поля")
                return

            doctor_name = selected_doctor.split(' (')[0]
            doctor = next((d for d in doctors if d['name'] == doctor_name), None)
            if not doctor:
                messagebox.showerror("Ошибка", "Врач не найден")
                return

            def task():
                try:
                    self.db.update_appointment(
                        apt_id=apt_id,
                        doctor_id=doctor['id'],
                        appointment_time=new_time,
                        appointment_date=new_date
                    )
                    self.ui_queue.put(lambda: messagebox.showinfo("Успех", "Запись успешно изменена!"))
                    self.ui_queue.put(dialog.destroy)
                    self.ui_queue.put(lambda: self.refresh_appointments())
                except Exception as e:
                    self.ui_queue.put(lambda: messagebox.showerror("Ошибка", str(e)))

            threading.Thread(target=task, daemon=True).start()

        ttk.Button(btn_frame, text="Сохранить", command=save_changes,
                   style="Ok.TButton", width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Danger.TButton", width=15).pack(side='left', padx=5)

    def invite_from_appointment(self):
        """Пригласить пациента из записи в очередь"""
        selected = self.appointments_tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите запись")
            return

        apt_id = int(selected[0])
        item = self.appointments_tree.item(selected[0])
        patient_name = item['values'][1]
        doctor_name = item['values'][4]

        # Проверяем статус врача
        def task():
            try:
                doctors = self.db.get_doctors()
                doctor = next((d for d in doctors if d['name'] == doctor_name), None)

                if not doctor:
                    self.ui_queue.put(lambda: messagebox.showerror("Ошибка", "Врач не найден"))
                    return

                # Проверяем статус врача - только "свободен" позволяет добавить в очередь
                if doctor['status'].lower() != 'свободен':
                    self.ui_queue.put(lambda: messagebox.showwarning(
                        "Предупреждение",
                        f"Врач {doctor_name} сейчас {doctor['status']}.\nЗапись попадёт в очередь только когда врач будет свободен."
                    ))
                    return

                # Добавляем в очередь
                self.db.add_to_queue(apt_id)
                self.ui_queue.put(lambda: messagebox.showinfo("Успех", f"Пациент {patient_name} добавлен в очередь"))
                self.ui_queue.put(lambda: self.refresh_queue())
                if self.patient_display and self.patient_display.winfo_exists():
                    self.ui_queue.put(lambda: self.patient_display.refresh())

            except Exception as e:
                self.ui_queue.put(lambda: messagebox.showerror("Ошибка", f"Не удалось добавить в очередь: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def cancel_appointment_with_search(self):
        """Отмена записи с поиском по имени"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Отменить запись")
        dialog.geometry("800x600")
        dialog.minsize(800, 600)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="ПОИСК И ОТМЕНА ЗАПИСИ",
                  font=('Arial', 16, 'bold')).pack(pady=20)

        # Поле поиска
        search_frame = ttk.Frame(dialog)
        search_frame.pack(fill='x', padx=20, pady=10)

        ttk.Label(search_frame, text="Имя пациента:").pack(side='left', padx=5)
        search_entry = ttk.Entry(search_frame, width=30)
        search_entry.pack(side='left', padx=5)

        # Результаты поиска
        results_frame = ttk.Frame(dialog)
        results_frame.pack(fill='both', expand=True, padx=20, pady=10)

        ttk.Label(results_frame, text="Результаты поиска:",
                  font=('Arial', 12, 'bold')).pack(anchor='w', pady=5)

        results_tree = ttk.Treeview(results_frame,
                                    columns=('date', 'time', 'patient', 'phone', 'doctor'),
                                    show='headings', height=15)
        results_tree.heading('date', text='Дата')
        results_tree.heading('time', text='Время')
        results_tree.heading('patient', text='Пациент')
        results_tree.heading('phone', text='Телефон')
        results_tree.heading('doctor', text='Врач')
        results_tree.column('date', width=100)
        results_tree.column('time', width=80)
        results_tree.column('patient', width=150)
        results_tree.column('phone', width=120)
        results_tree.column('doctor', width=120)
        results_tree.pack(fill='both', expand=True)

        def search_appointments():
            name = search_entry.get().strip()
            if not name:
                messagebox.showwarning("Предупреждение", "Введите имя пациента")
                return

            # Очищаем результаты
            for item in results_tree.get_children():
                results_tree.delete(item)

            def task():
                try:
                    appointments = self.db.search_appointments(name)

                    def update_ui():
                        if not appointments:
                            messagebox.showinfo("Результат", "Записи не найдены")
                            return

                        for apt in appointments:
                            results_tree.insert('', 'end', iid=str(apt['id']), values=(
                                apt.get('appointment_date', ''),
                                apt.get('appointment_time', ''),
                                apt.get('patient_name', ''),
                                apt.get('phone', ''),
                                apt.get('doctor_name', '')
                            ))

                    self.ui_queue.put(update_ui)
                except Exception as e:
                    self.ui_queue.put(lambda: messagebox.showerror("Ошибка", f"Ошибка поиска: {e}"))

            threading.Thread(target=task, daemon=True).start()

        def cancel_selected():
            selected = results_tree.selection()
            if not selected:
                messagebox.showwarning("Предупреждение", "Выберите запись для отмены")
                return

            apt_id = int(selected[0])
            item = results_tree.item(selected[0])
            patient_name = item['values'][2]

            if messagebox.askyesno("Подтверждение", f"Отменить запись для {patient_name}?"):
                def task():
                    try:
                        self.db.cancel_appointment(apt_id)
                        # Удаляем из дерева поиска
                        self.ui_queue.put(lambda: results_tree.delete(selected[0]))
                        # Удаляем из основного списка (если он уже отображается)
                        self.ui_queue.put(lambda: self.appointments_tree.delete(str(apt_id)) if self.appointments_tree.exists(str(apt_id)) else None)
                        self.ui_queue.put(lambda: messagebox.showinfo("Успех", "Запись отменена"))
                        self.ui_queue.put(lambda: self.refresh_appointments())
                    except Exception as e:
                        self.ui_queue.put(lambda: messagebox.showerror("Ошибка", str(e)))

                threading.Thread(target=task, daemon=True).start()

        # Двойной клик по строке — отмена выбранной записи
        results_tree.bind('<Double-1>', lambda e: cancel_selected())

        # Кнопки
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side='bottom', fill='x', pady=10)

        ttk.Button(btn_frame, text="🔍 Искать", command=search_appointments,
                   style="Primary.TButton", width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="❌ Отменить запись", command=cancel_selected,
                   style="Danger.TButton", width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=dialog.destroy,
                   style="Warn.TButton", width=15).pack(side='left', padx=5)

        # Автопоиск при вводе
        search_entry.bind('<Return>', lambda e: search_appointments())

    # ---------- Статистика ----------
    def show_statistics(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Статистика")
        dialog.geometry("800x600")
        dialog.minsize(800, 600)
        dialog.transient(self.root)

        tk.Label(dialog, text="СТАТИСТИКА КЛИНИКИ", font=('Arial', 18, 'bold'),
                 fg='#1976D2').pack(pady=20)

        stats_frame = tk.LabelFrame(dialog, text="Загрузка...", font=('Arial', 14, 'bold'),
                                    padx=20, pady=20)
        stats_frame.pack(fill='both', padx=20, pady=10)

        def load_stats(stats, error):
            if error:
                messagebox.showerror("Ошибка", f"Не удалось загрузить статистику: {error}")
                dialog.destroy()
                return

            stats_frame.configure(text="Общая статистика")

            tk.Label(stats_frame, text=f"Всего записей: {stats['total']}",
                     font=('Arial', 13)).pack(anchor='w', pady=5)
            tk.Label(stats_frame, text=f"Активных записей: {stats['active']}",
                     font=('Arial', 13), fg='#4CAF50').pack(anchor='w', pady=5)
            tk.Label(stats_frame, text=f"Отменённых записей: {stats['cancelled']}",
                     font=('Arial', 13), fg='#F44336').pack(anchor='w', pady=5)
            tk.Label(stats_frame, text=f"Принято пациентов: {stats['completed']}",
                     font=('Arial', 13), fg='#2196F3').pack(anchor='w', pady=5)

            doctors_frame = tk.LabelFrame(dialog, text="Эффективность врачей",
                                          font=('Arial', 14, 'bold'), padx=20, pady=20)
            doctors_frame.pack(fill='both', padx=20, pady=10)

            for doc in stats.get('doctors', []):
                completed = doc.get('completed', doc.get('completed_count', 0))
                tk.Label(doctors_frame,
                         text=f"{doc['name']}: {completed} пациентов",
                         font=('Arial', 12)).pack(anchor='w', pady=3)

        self.db.get_stats_async(load_stats)

    # ---------- Экран очереди ----------
    def open_patient_display(self):
        if self.patient_display is None or not self.patient_display.winfo_exists():
            self.patient_display = PatientDisplay(self.root, self.db)
        else:
            self.patient_display.lift()

    # ---------- Обновление данных ----------
    def refresh_all(self):
        if self.is_refreshing:
            return

        self.is_refreshing = True
        self.refresh_doctors()
        self.refresh_queue()
        self.refresh_appointments()

        def done():
            self.is_refreshing = False
            if self.patient_display and self.patient_display.winfo_exists():
                self.patient_display.refresh()

        self.ui_queue.put(done)

    def refresh_doctors(self):
        def callback(doctors, error):
            if error:
                return

            selected = self.doctors_tree.selection()
            selected_name = None
            if selected:
                item = self.doctors_tree.item(selected[0])
                selected_name = item['values'][0]

            for item in self.doctors_tree.get_children():
                self.doctors_tree.delete(item)

            for doc in doctors:
                self.doctors_tree.insert('', 'end', values=(doc['name'], doc['room'], doc['status']))

            # Восстанавливаем выделение
            if selected_name:
                for item in self.doctors_tree.get_children():
                    if self.doctors_tree.item(item)['values'][0] == selected_name:
                        self.doctors_tree.selection_set(item)
                        break

        self.db.get_doctors_async(callback)

    def refresh_queue(self):
        def callback(queue, error):
            if error:
                return

            selected = self.queue_tree.selection()
            selected_id = selected[0] if selected else None

            for item in self.queue_tree.get_children():
                self.queue_tree.delete(item)

            for item in queue:
                self.queue_tree.insert('', 'end', iid=str(item['id']), values=(
                    item['patient_name'],
                    item.get('service_name', ''),
                    item['doctor_name'],
                    item['room'],
                    item['status']
                ))

            if selected_id and self.queue_tree.exists(selected_id):
                self.queue_tree.selection_set(selected_id)
                self.queue_tree.focus(selected_id)

        self.db.get_queue_async(callback)

    def refresh_appointments(self):
        date_str = self.current_date.strftime("%Y-%m-%d")

        def callback(apts, error):
            if error:
                return

            selected = self.appointments_tree.selection()
            selected_id = selected[0] if selected else None

            for item in self.appointments_tree.get_children():
                self.appointments_tree.delete(item)

            for apt in apts:
                self.appointments_tree.insert('', 'end', iid=str(apt['id']), values=(
                    apt['appointment_time'],
                    apt['patient_name'],
                    apt['phone'],
                    apt.get('service_name', ''),
                    apt['doctor_name']
                ))

            if selected_id and self.appointments_tree.exists(selected_id):
                self.appointments_tree.selection_set(selected_id)
                self.appointments_tree.focus(selected_id)

        self.db.get_appointments_async(date_str, callback)

    def start_auto_refresh(self):
        """Автообновление каждые 10 секунд"""

        def auto_refresh():
            while True:
                time.sleep(CHECK_INTERVAL)
                try:
                    self.ui_queue.put(self.refresh_all)
                except:
                    break

        thread = threading.Thread(target=auto_refresh, daemon=True)
        thread.start()

    def announce_patient(self, patient_name, room):
        """Объявление пациента"""
        if HAS_TTS:
            def announce():
                try:
                    winsound.MessageBeep()
                    winsound.Beep(1000, 300)
                except:
                    pass

                if TTS_ENGINE:
                    try:
                        text = f"Приглашаем пациента {patient_name} в {room}"
                        TTS_ENGINE.say(text)
                        TTS_ENGINE.runAndWait()
                    except:
                        pass

            threading.Thread(target=announce, daemon=True).start()


class PatientDisplay(tk.Toplevel):
    """Экран отображения очереди для пациентов"""

    def __init__(self, master, db):
        super().__init__(master)
        self.db = db
        self.title("Электронная очередь")
        self.geometry("1920x1080")
        self.configure(bg='white')

        header = tk.Frame(self, bg='#2196F3', height=120)
        header.pack(fill='x')

        title = tk.Label(header, text="СТОМАТОЛОГИЧЕСКАЯ КЛИНИКА",
                         font=('Arial', 48, 'bold'), bg='#2196F3', fg='white')
        title.pack(pady=30)

        self.rooms_container = tk.Frame(self, bg='white')
        self.rooms_container.pack(fill='both', expand=True, padx=40, pady=40)

        self.refresh()
        self.auto_refresh()

    def refresh(self):
        def callback_doctors(doctors, error):
            if error:
                return

            def callback_queue(queue, error2):
                if error2:
                    return

                for widget in self.rooms_container.winfo_children():
                    widget.destroy()

                for i, doctor in enumerate(doctors):
                    row = i // 2
                    col = i % 2
                    self.create_doctor_card(doctor, queue, row, col)

            self.db.get_queue_async(callback_queue)

        self.db.get_doctors_async(callback_doctors)

    def create_doctor_card(self, doctor, queue, row, col):
        card = tk.Frame(self.rooms_container, bg='#f5f5f5', relief='raised', borderwidth=3)
        card.grid(row=row, column=col, padx=20, pady=20, sticky='nsew')

        self.rooms_container.grid_rowconfigure(row, weight=1)
        self.rooms_container.grid_columnconfigure(col, weight=1)

        tk.Label(card, text=doctor['room'], font=('Arial', 36, 'bold'), bg='#f5f5f5').pack(pady=15)
        tk.Label(card, text=doctor['name'], font=('Arial', 24), bg='#f5f5f5').pack(pady=5)
        tk.Frame(card, bg='#2196F3', height=3).pack(fill='x', pady=15)

        current = None
        waiting_count = 0

        for item in queue:
            if item['doctor_id'] == doctor['id']:
                if item['status'] == 'в_работе':
                    current = item
                elif item['status'] in ['готов', 'ожидание']:
                    if not current:
                        current = item
                    waiting_count += 1

        if current:
            if current['status'] == 'в_работе':
                tk.Label(card, text="ИДЁТ ПРИЁМ", font=('Arial', 28, 'bold'),
                         bg='#f5f5f5', fg='#4CAF50').pack(pady=10)
                tk.Label(card, text=current['patient_name'], font=('Arial', 32, 'bold'),
                         bg='#f5f5f5', fg='#2196F3').pack(pady=10)
            elif current['status'] == 'готов':
                tk.Label(card, text="ПРИГЛАШАЕМ", font=('Arial', 28, 'bold'),
                         bg='#f5f5f5', fg='#FF9800').pack(pady=10)
                tk.Label(card, text=current['patient_name'], font=('Arial', 32, 'bold'),
                         bg='#f5f5f5', fg='#2196F3').pack(pady=10)
            else:
                tk.Label(card, text="ОЖИДАНИЕ", font=('Arial', 28, 'bold'),
                         bg='#f5f5f5', fg='#FF9800').pack(pady=10)
                if waiting_count > 0:
                    tk.Label(card, text=f"{waiting_count} чел.", font=('Arial', 32, 'bold'),
                             bg='#f5f5f5').pack(pady=10)
        else:
            tk.Label(card, text="СВОБОДНО", font=('Arial', 36, 'bold'),
                     bg='#f5f5f5', fg='#4CAF50').pack(pady=30)

    def auto_refresh(self):
        self.refresh()
        self.after(3000, self.auto_refresh)


if __name__ == "__main__":
    root = tk.Tk()
    app = AdminPanel(root)
    root.mainloop()
