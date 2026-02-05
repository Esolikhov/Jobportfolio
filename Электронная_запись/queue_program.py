#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПРОГРАММА УПРАВЛЕНИЯ ЭЛЕКТРОННОЙ ОЧЕРЕДЬЮ
С ПОЛНЫМ ФУНКЦИОНАЛОМ
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta
import sqlite3
import threading
import time
import re
import pyttsx3
import winsound

DATABASE = 'dental_clinic.db'
CHECK_INTERVAL = 10
TTS_ENGINE = None

try:
    TTS_ENGINE = pyttsx3.init()
    TTS_ENGINE.setProperty('rate', 150)
    TTS_ENGINE.setProperty('volume', 1.0)
except:
    print("TTS не доступен")

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
    # tk widgets only (ttk handled by style)
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        _safe_config(widget, bg=theme["bg"])
    if isinstance(widget, tk.Frame):
        try:
            current = str(widget.cget("bg")).lower()
        except Exception:
            current = ""
        # сохраняем "шапку" в фирменном цвете
        if current in ("#1976d2", "rgb(25,118,210)"):
            _safe_config(widget, bg=theme["primary"])
        else:
            _safe_config(widget, bg=theme["bg"])
    if isinstance(widget, tk.LabelFrame):
        _safe_config(widget, bg=theme["card"], fg=theme["text"])
    if isinstance(widget, tk.Label):
        bg = widget.cget("bg")
        # if label was on card, keep it as card
        new_bg = theme["card"] if bg.lower() in ("white", "#ffffff") else theme["bg"]
        _safe_config(widget, bg=new_bg, fg=theme["text"])
    if isinstance(widget, tk.Button):
        # Сохраняем кнопки с явно заданным цветом (например, красные/зелёные).
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
    def __init__(self):
        self.db_name = DATABASE
        conn = self.get_connection()
        conn.close()

    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        self.ensure_schema(conn)
        return conn

    def ensure_schema(self, conn):
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            room TEXT NOT NULL,
            specialization TEXT,
            status TEXT DEFAULT 'свободен',
            is_active INTEGER DEFAULT 1
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            phone TEXT,
            doctor_id INTEGER,
            appointment_date TEXT,
            appointment_time TEXT,
            status TEXT DEFAULT 'активна',
            is_walk_in INTEGER DEFAULT 0,
            service_name TEXT,
            kind TEXT DEFAULT 'patient'
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER,
            patient_name TEXT,
            doctor_id INTEGER,
            room TEXT,
            status TEXT,
            called_at TEXT,
            started_at TEXT,
            finished_at TEXT
        )
        """)

        conn.commit()

    def get_services_list(self):
        """Справочник услуг: берём уникальные значения из БД + базовые варианты."""
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT DISTINCT TRIM(service_name) as s FROM appointments WHERE service_name IS NOT NULL AND TRIM(service_name) <> ''"
        ).fetchall()
        conn.close()

        services = sorted({r["s"] for r in rows if r and r["s"]})
        defaults = [
            "Консультация",
            "Лечение кариеса",
            "Удаление зуба",
            "Чистка (профгигиена)",
            "Пломба",
            "Ортодонтия",
            "Имплантация",
            "Рентген",
        ]
        for d in defaults:
            if d not in services:
                services.append(d)
        return services

    def get_queue_item(self, queue_id: int):
        conn = self.get_connection()
        row = conn.execute(
            """SELECT q.*, d.room as doctor_room, d.status as doctor_status
               FROM queue q
               JOIN doctors d ON d.id = q.doctor_id
               WHERE q.id = ?""",
            (queue_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def mark_appointment_completed(self, appointment_id: int) -> None:
        """Помечаем запись как завершённую, чтобы она исчезла из 'записей на сегодня'."""
        conn = self.get_connection()
        conn.execute("UPDATE appointments SET status = 'завершена' WHERE id = ?", (appointment_id,))
        conn.commit()
        conn.close()

    def get_doctors(self):
        conn = self.get_connection()
        doctors = conn.execute("SELECT * FROM doctors WHERE is_active = 1 ORDER BY id").fetchall()
        conn.close()
        return [dict(row) for row in doctors]

    def get_appointments(self, date):
        conn = self.get_connection()
        apts = conn.execute("""
            SELECT a.*, d.name as doctor_name, d.room 
            FROM appointments a
            JOIN doctors d ON a.doctor_id = d.id
            WHERE a.appointment_date = ? AND a.status = 'активна'
            ORDER BY a.appointment_time
        """, (date,)).fetchall()
        conn.close()
        return [dict(row) for row in apts]

    def is_doctor_available(self, doctor_id: int, date: str, time_str: str, exclude_appointment_id: int = None) -> bool:
        """Проверяем, свободен ли врач в указанное время (учитываем пациентов, перерывы и выходные)."""
        conn = self.get_connection()
        params = [doctor_id, date, time_str]
        sql = """SELECT COUNT(1) as cnt
                 FROM appointments
                 WHERE doctor_id = ?
                   AND appointment_date = ?
                   AND appointment_time = ?
                   AND status = 'активна'
                   AND kind IN ('patient','break','dayoff')"""
        if exclude_appointment_id is not None:
            sql += " AND id <> ?"
            params.append(exclude_appointment_id)
        row = conn.execute(sql, tuple(params)).fetchone()
        conn.close()
        return (row["cnt"] if hasattr(row, "__getitem__") else row[0]) == 0

    def update_appointment(self, appointment_id: int, *, doctor_id: int, date: str, time_str: str,
                           patient_name: str, phone: str, service_name: str, kind: str = "patient") -> None:
        conn = self.get_connection()
        conn.execute(
            """UPDATE appointments
                   SET doctor_id = ?, appointment_date = ?, appointment_time = ?,
                       patient_name = ?, phone = ?, service_name = ?, kind = ?
                 WHERE id = ?""",
            (doctor_id, date, time_str, patient_name, phone, service_name, kind, appointment_id),
        )
        conn.commit()
        conn.close()

    def get_queue(self):
        conn = self.get_connection()
        queue = conn.execute("""
            SELECT q.*, d.name as doctor_name, a.service_name
            FROM queue q
            JOIN doctors d ON q.doctor_id = d.id
            LEFT JOIN appointments a ON a.id = q.appointment_id
            WHERE q.status NOT IN ('завершён', 'не_пришёл', 'отменён')
            ORDER BY q.called_at
        """).fetchall()
        conn.close()
        return [dict(row) for row in queue]

    def add_to_queue(self, appointment_id, patient_name, doctor_id, room, status='вызван'):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO queue (appointment_id, patient_name, doctor_id, room, status, called_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (appointment_id, patient_name, doctor_id, room, status, datetime.now().isoformat()))
        conn.commit()
        queue_id = cursor.lastrowid
        conn.close()
        return queue_id

    def update_queue_status(self, queue_id, status, field=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        if field == 'started':
            cursor.execute("UPDATE queue SET status = ?, started_at = ? WHERE id = ?",
                           (status, datetime.now().isoformat(), queue_id))
        elif field == 'finished':
            cursor.execute("UPDATE queue SET status = ?, finished_at = ? WHERE id = ?",
                           (status, datetime.now().isoformat(), queue_id))
        else:
            cursor.execute("UPDATE queue SET status = ? WHERE id = ?", (status, queue_id))
        conn.commit()
        conn.close()

    def update_doctor_status(self, doctor_id, status):
        conn = self.get_connection()
        conn.execute("UPDATE doctors SET status = ? WHERE id = ?", (status, doctor_id))
        conn.commit()
        conn.close()

    def get_doctor_status(self, doctor_id):
        conn = self.get_connection()
        result = conn.execute("SELECT status FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
        conn.close()
        return result['status'] if result else None

    def cancel_appointment(self, apt_id):
        conn = self.get_connection()
        conn.execute("UPDATE appointments SET status = 'отменена' WHERE id = ?", (apt_id,))
        conn.commit()
        conn.close()

    def create_walk_in_appointment(self, patient_name: str, phone: str, doctor_id: int,
                                   service_name: str | None = None) -> int:
        """Создать запись 'без предварительной записи' (walk-in)."""
        now = datetime.now()
        date = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M')
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO appointments (patient_name, phone, doctor_id, appointment_date, appointment_time, is_walk_in, service_name, status)
               VALUES (?, ?, ?, ?, ?, 1, ?, 'активна')""",
            (patient_name, phone, doctor_id, date, time_str, service_name),
        )
        conn.commit()
        apt_id = cur.lastrowid
        conn.close()
        return apt_id

    def search_appointments(self, search_text):
        conn = self.get_connection()
        apts = conn.execute("""
            SELECT a.*, d.name as doctor_name, d.room
            FROM appointments a
            JOIN doctors d ON a.doctor_id = d.id
            WHERE (a.patient_name LIKE ? OR a.phone LIKE ?) AND a.status = 'активна'
            ORDER BY a.appointment_date, a.appointment_time
        """, (f'%{search_text}%', f'%{search_text}%')).fetchall()
        conn.close()
        return [dict(row) for row in apts]

    def get_stats(self):
        conn = self.get_connection()
        total = conn.execute("SELECT COUNT(*) as cnt FROM appointments").fetchone()['cnt']
        active = conn.execute("SELECT COUNT(*) as cnt FROM appointments WHERE status = 'активна'").fetchone()['cnt']
        cancelled = conn.execute("SELECT COUNT(*) as cnt FROM appointments WHERE status = 'отменена'").fetchone()['cnt']
        completed = conn.execute("SELECT COUNT(*) as cnt FROM queue WHERE status = 'завершён'").fetchone()['cnt']

        doctors_stats = conn.execute("""
            SELECT d.name, 
                   COUNT(CASE WHEN q.status = 'завершён' THEN 1 END) as completed,
                   d.specialization
            FROM doctors d
            LEFT JOIN queue q ON d.id = q.doctor_id
            WHERE d.is_active = 1
            GROUP BY d.id, d.name, d.specialization
        """).fetchall()

        conn.close()
        return {
            'total': total,
            'active': active,
            'cancelled': cancelled,
            'completed': completed,
            'doctors': [dict(row) for row in doctors_stats]
        }


class AdminPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Система управления очередью - Стоматология")
        # ИСПРАВЛЕНО: увеличены размеры главного окна
        self.root.geometry("1400x950")
        self.root.minsize(1200, 850)
        self.root.resizable(True, True)

        self.db = Database()
        # Тема (Light/Dark)
        self.theme = ThemeManager(self.root, initial="light")
        self.patient_display = None
        self.current_date = datetime.now().strftime('%Y-%m-%d')

        self.create_widgets()
        apply_theme_recursive(self.root, self.theme.t)
        self.auto_check_thread = threading.Thread(target=self.auto_check_appointments, daemon=True)
        self.auto_check_thread.start()
        self.refresh_all()

    def create_widgets(self):
        # Верхняя панель
        top_frame = tk.Frame(self.root, bg='#1976D2', height=100)
        top_frame.pack(fill='x')
        top_frame.pack_propagate(False)

        title = tk.Label(top_frame, text="СИСТЕМА УПРАВЛЕНИЯ ЭЛЕКТРОННОЙ ОЧЕРЕДЬЮ",
                         font=('Arial', 28, 'bold'), bg='#1976D2', fg='white')
        title.pack(pady=30)

        theme_btn = ttk.Button(top_frame, text="Сменить тему", style="Primary.TButton", command=self.toggle_theme)
        theme_btn.pack(side='right', padx=15, pady=20)

        # Основной контейнер
        main = tk.Frame(self.root, bg='#f5f5f5')
        main.pack(fill='both', expand=True, padx=15, pady=15)

        # Левая панель
        left = tk.Frame(main, bg='#f5f5f5')
        left.pack(side='left', fill='both', expand=True, padx=5)

        # Врачи
        doctors_frame = tk.LabelFrame(left, text="ВРАЧИ И СТАТУСЫ", font=('Arial', 14, 'bold'),
                                      bg='white', padx=15, pady=15)
        doctors_frame.pack(fill='x', pady=5)

        self.doctors_tree = ttk.Treeview(doctors_frame, columns=('Врач', 'Кабинет', 'Статус'),
                                         show='headings', height=3)
        self.doctors_tree.heading('Врач', text='Врач')
        self.doctors_tree.heading('Кабинет', text='Кабинет')
        self.doctors_tree.heading('Статус', text='Статус')
        self.doctors_tree.column('Врач', width=350)
        self.doctors_tree.column('Кабинет', width=120)
        self.doctors_tree.column('Статус', width=120)
        self.doctors_tree.pack(fill='x', pady=5)

        # Кнопки управления статусом врача
        doctor_btn_frame = tk.Frame(doctors_frame, bg='white')
        doctor_btn_frame.pack(fill='x', pady=5)

        tk.Button(doctor_btn_frame, text="Свободен", bg='#4CAF50', fg='white', font=('Arial', 10, 'bold'),
                  command=lambda: self.change_doctor_status('свободен')).pack(side='left', padx=5)
        tk.Button(doctor_btn_frame, text="Занят", bg='#F44336', fg='white', font=('Arial', 10, 'bold'),
                  command=lambda: self.change_doctor_status('занят')).pack(side='left', padx=5)
        tk.Button(doctor_btn_frame, text="Перерыв", bg='#FF9800', fg='white', font=('Arial', 10, 'bold'),
                  command=lambda: self.change_doctor_status('перерыв')).pack(side='left', padx=5)

        tk.Button(doctor_btn_frame, text="Выходной", bg='#795548', fg='white', font=('Arial', 10, 'bold'),
                  command=lambda: self.change_doctor_status('выходной')).pack(side='left', padx=5)

        # Очередь
        queue_frame = tk.LabelFrame(left, text="ТЕКУЩАЯ ОЧЕРЕДЬ", font=('Arial', 14, 'bold'),
                                    bg='white', padx=15, pady=15)
        queue_frame.pack(fill='both', expand=True, pady=5)

        self.queue_tree = ttk.Treeview(queue_frame, columns=('Пациент', 'Услуга', 'Врач', 'Кабинет', 'Статус'),
                                       show='headings', height=15)
        self.queue_tree.heading('Пациент', text='Пациент')
        self.queue_tree.heading('Услуга', text='Услуга')
        self.queue_tree.heading('Врач', text='Врач')
        self.queue_tree.heading('Кабинет', text='Кабинет')
        self.queue_tree.heading('Статус', text='Статус')
        self.queue_tree.column('Пациент', width=200)
        self.queue_tree.column('Услуга', width=200)
        self.queue_tree.column('Врач', width=200)
        self.queue_tree.column('Кабинет', width=100)
        self.queue_tree.column('Статус', width=120)
        self.queue_tree.pack(fill='both', expand=True)

        # Правая панель
        right = tk.Frame(main, bg='#f5f5f5')
        right.pack(side='right', fill='both', expand=True, padx=5)

        # ===== КНОПКИ УПРАВЛЕНИЯ (СКРОЛЛИНГ) =====
        # Перенесено наверх правой панели (по запросу): кнопки всегда сверху,
        # а таблица записей ниже со скроллом.
        controls_container = tk.Frame(right, bg='white')
        controls_container.pack(fill='x', expand=False, pady=5)

        tk.Label(
            controls_container,
            text="УПРАВЛЕНИЕ",
            font=('Arial', 14, 'bold'),
            bg='white'
        ).pack(anchor='w', padx=15, pady=(8, 0))

        # Canvas + Scrollbar (вертикальный скролл для кнопок)
        controls_canvas = tk.Canvas(
            controls_container,
            bg='white',
            highlightthickness=0,
            height=230  # регулируй при необходимости (200–300)
        )
        controls_canvas.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=8)

        controls_scrollbar = ttk.Scrollbar(
            controls_container,
            orient='vertical',
            command=controls_canvas.yview
        )
        controls_scrollbar.pack(side='right', fill='y', padx=(0, 10), pady=8)

        controls_canvas.configure(yscrollcommand=controls_scrollbar.set)

        # Внутренний контейнер кнопок
        buttons_frame = tk.Frame(controls_canvas, bg='white')
        controls_canvas.create_window((0, 0), window=buttons_frame, anchor='nw')

        # сетка 2 колонки
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_columnconfigure(1, weight=1)

        btn_style = {
            'font': ('Arial', 11, 'bold'),
            'height': 2,
            'width': 18
        }

        buttons = [
            ("Начать приём", self.start_appointment, "#4CAF50"),
            ("Завершить приём", self.finish_appointment, "#FF9800"),
            ("Отменить запись", self.cancel_appointment_dialog, "#F44336"),
            ("Изменить запись", self.edit_appointment_dialog, "#3F51B5"),
            ("Пригласить", self.invite_selected_appointment, "#009688"),
            ("Без записи", self.add_walk_in_patient, "#00BCD4"),
            ("Экран пациентов", self.open_patient_display, "#607D8B"),
            ("Статистика", self.show_statistics, "#9C27B0"),
            ("Обновить", self.refresh_all, "#2196F3"),
        ]

        for i, (text, command, color) in enumerate(buttons):
            tk.Button(
                buttons_frame,
                text=text,
                bg=color,
                fg='white',
                command=command,
                **btn_style
            ).grid(
                row=i // 2,
                column=i % 2,
                padx=6,
                pady=6,
                sticky='ew'
            )

        # обновляем область прокрутки
        buttons_frame.update_idletasks()
        controls_canvas.configure(scrollregion=controls_canvas.bbox("all"))

        # прокрутка колесом мыши по кнопкам (когда курсор над блоком управления)
        def _controls_on_mousewheel(event):
            controls_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        controls_canvas.bind("<Enter>", lambda e: controls_canvas.bind_all("<MouseWheel>", _controls_on_mousewheel))
        controls_canvas.bind("<Leave>", lambda e: controls_canvas.unbind_all("<MouseWheel>"))

        # ----------------------------
        # ЗАПИСИ НА ПРИЁМ (со скроллом)
        # ----------------------------
        date_frame = tk.LabelFrame(
            right,
            text="ЗАПИСИ НА ПРИЁМ",
            font=('Arial', 14, 'bold'),
            bg='white',
            padx=15,
            pady=15
        )
        date_frame.pack(fill='both', expand=True, pady=5)

        date_btn_frame = tk.Frame(date_frame, bg='white')
        date_btn_frame.pack(fill='x', pady=5)

        tk.Button(date_btn_frame, text="Сегодня", bg='#2196F3', fg='white', font=('Arial', 11, 'bold'),
                  command=self.show_today).pack(side='left', padx=5)
        tk.Button(date_btn_frame, text="Завтра", bg='#2196F3', fg='white', font=('Arial', 11, 'bold'),
                  command=self.show_tomorrow).pack(side='left', padx=5)
        tk.Button(date_btn_frame, text="Выбрать дату", bg='#2196F3', fg='white', font=('Arial', 11, 'bold'),
                  command=self.select_date).pack(side='left', padx=5)

        self.date_label = tk.Label(
            date_frame,
            text=f"Дата: {self.format_date(self.current_date)}",
            font=('Arial', 12, 'bold'),
            bg='white',
            fg='#1976D2'
        )
        self.date_label.pack(pady=5)

        # Контейнер таблицы + скроллбары (вниз и влево/вправо)
        apt_table = tk.Frame(date_frame, bg='white')
        apt_table.pack(fill='both', expand=True, pady=5)

        apt_scroll_y = ttk.Scrollbar(apt_table, orient='vertical')
        apt_scroll_x = ttk.Scrollbar(apt_table, orient='horizontal')

        # Таблица записей
        self.appointments_tree = ttk.Treeview(
            apt_table,
            columns=('Время', 'Пациент', 'Телефон', 'Услуга', 'Врач'),
            show='headings',
            height=15,
            yscrollcommand=apt_scroll_y.set,
            xscrollcommand=apt_scroll_x.set
        )
        apt_scroll_y.config(command=self.appointments_tree.yview)
        apt_scroll_x.config(command=self.appointments_tree.xview)

        self.appointments_tree.heading('Время', text='Время')
        self.appointments_tree.heading('Пациент', text='Пациент')
        self.appointments_tree.heading('Телефон', text='Телефон')
        self.appointments_tree.heading('Услуга', text='Услуга')
        self.appointments_tree.heading('Врач', text='Врач')

        self.appointments_tree.column('Время', width=70, stretch=False)
        self.appointments_tree.column('Пациент', width=170, stretch=False)
        self.appointments_tree.column('Телефон', width=140, stretch=False)
        self.appointments_tree.column('Услуга', width=220, stretch=False)
        self.appointments_tree.column('Врач', width=260, stretch=False)

        # layout: tree + вертикальный + горизонтальный скролл
        self.appointments_tree.grid(row=0, column=0, sticky='nsew')
        apt_scroll_y.grid(row=0, column=1, sticky='ns')
        apt_scroll_x.grid(row=1, column=0, sticky='ew')

        apt_table.grid_rowconfigure(0, weight=1)
        apt_table.grid_columnconfigure(0, weight=1)

        # колесо мыши — вертикальный скролл таблицы; Shift+колесо — горизонтальный
        def _apt_on_mousewheel(event):
            self.appointments_tree.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _apt_on_shift_mousewheel(event):
            # горизонтальная прокрутка (влево/вправо)
            self.appointments_tree.xview_scroll(int(-1 * (event.delta / 120)), "units")

        self.appointments_tree.bind("<Enter>",
                                    lambda e: self.appointments_tree.bind_all("<MouseWheel>", _apt_on_mousewheel))
        self.appointments_tree.bind("<Leave>", lambda e: self.appointments_tree.unbind_all("<MouseWheel>"))
        self.appointments_tree.bind_all("<Shift-MouseWheel>", _apt_on_shift_mousewheel)

    def toggle_theme(self):
        """Переключение светлой/тёмной темы."""
        self.theme.toggle()
        # применяем к tk-виджетам (часть интерфейса на tk.*)
        apply_theme_recursive(self.root, self.theme.t)
        # обновляем заголовки, если нужно
        try:
            self.date_label.config(bg=self.theme.t["card"], fg=self.theme.t["primary"])
        except Exception:
            pass

    def format_date(self, date_str):
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"

    def show_today(self):
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        self.date_label.config(text=f"Дата: {self.format_date(self.current_date)}")
        self.refresh_all()

    def show_tomorrow(self):
        tomorrow = datetime.now() + timedelta(days=1)
        self.current_date = tomorrow.strftime('%Y-%m-%d')
        self.date_label.config(text=f"Дата: {self.format_date(self.current_date)}")
        self.refresh_all()

    def select_date(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Выбор даты")
        dialog.geometry("300x150")

        tk.Label(dialog, text="Введите дату (ДД.ММ.ГГГГ):", font=('Arial', 12)).pack(pady=20)
        date_entry = tk.Entry(dialog, font=('Arial', 12), width=20)
        date_entry.pack(pady=10)

        def apply_date():
            try:
                dt = datetime.strptime(date_entry.get(), '%d.%m.%Y')
                self.current_date = dt.strftime('%Y-%m-%d')
                self.date_label.config(text=f"Дата: {self.format_date(self.current_date)}")
                dialog.destroy()
                self.refresh_all()
            except:
                messagebox.showerror("Ошибка", "Неверный формат даты")

        tk.Button(dialog, text="Применить", command=apply_date, bg='#2196F3',
                  fg='white', font=('Arial', 11, 'bold')).pack(pady=10)

    def change_doctor_status(self, status):
        selected = self.doctors_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите врача")
            return

        item = self.doctors_tree.item(selected[0])
        doctor_name = item['values'][0]

        doctors = self.db.get_doctors()
        doctor_id = None
        for doc in doctors:
            if doc['name'] == doctor_name:
                doctor_id = doc['id']
                break

        if doctor_id:
            self.db.update_doctor_status(doctor_id, status)
            self.refresh_all()
            messagebox.showinfo("Успешно", f"Статус врача изменён на: {status}")

    def invite_selected_appointment(self):
        """Пригласить пациента по выбранной записи (с учётом статуса врача)."""
        selected = self.appointments_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите запись в правой таблице")
            return

        apt_id = int(selected[0])
        # проверим, не добавлен ли уже в очередь
        conn = self.db.get_connection()
        exists = conn.execute(
            "SELECT id FROM queue WHERE appointment_id = ? AND status NOT IN ('завершён','не_пришёл','отменён')",
            (apt_id,)).fetchone()
        if exists:
            conn.close()
            messagebox.showinfo("Информация", "Эта запись уже добавлена в очередь")
            return

        apt = conn.execute(
            """SELECT a.*, d.room, d.status as doctor_status
               FROM appointments a
               JOIN doctors d ON d.id = a.doctor_id
               WHERE a.id = ?""",
            (apt_id,),
        ).fetchone()
        conn.close()
        if not apt:
            messagebox.showerror("Ошибка", "Запись не найдена")
            return

        doctor_status = apt['doctor_status']
        # если врач не свободен — не приглашаем, ставим ожидание
        if doctor_status != 'свободен':
            self.db.add_to_queue(apt_id, apt['patient_name'], apt['doctor_id'], apt['room'], 'ожидание')
            self.refresh_all()
            messagebox.showwarning("Внимание", f"Врач сейчас: {doctor_status}. Пациент добавлен в ожидание.")
            return

        # врач свободен — приглашаем
        self.db.add_to_queue(apt_id, apt['patient_name'], apt['doctor_id'], apt['room'], 'готов')
        self.refresh_all()
        self.announce_patient(apt['patient_name'], apt['room'])

    def add_walk_in_patient(self):
        """Добавить пациента без записи (модальное окно, без автозакрытия)."""
        if hasattr(self, "_walkin_window") and self._walkin_window and self._walkin_window.winfo_exists():
            # уже открыто — просто поднимем
            self._walkin_window.lift()
            return

        doctors = self.db.get_doctors()
        if not doctors:
            messagebox.showerror("Ошибка", "Нет врачей в системе")
            return

        win = tk.Toplevel(self.root)
        self._walkin_window = win
        win.title("Пациент без записи")
        win.geometry("520x380")
        win.configure(bg="white")
        win.transient(self.root)
        win.grab_set()

        title = tk.Label(win, text="ПАЦИЕНТ БЕЗ ЗАПИСИ", font=('Arial', 16, 'bold'), bg="white", fg="#1976D2")
        title.pack(pady=10)

        form = tk.Frame(win, bg="white")
        form.pack(fill="both", expand=True, padx=20, pady=10)

        # Имя
        tk.Label(form, text="Имя пациента *", font=('Arial', 12, 'bold'), bg="white").grid(row=0, column=0, sticky="w",
                                                                                           pady=6)
        name_var = tk.StringVar()
        name_entry = tk.Entry(form, textvariable=name_var, font=('Arial', 12), width=30)
        name_entry.grid(row=0, column=1, sticky="w", pady=6)

        # Телефон
        tk.Label(form, text="Телефон", font=('Arial', 12, 'bold'), bg="white").grid(row=1, column=0, sticky="w", pady=6)
        phone_var = tk.StringVar()
        phone_entry = tk.Entry(form, textvariable=phone_var, font=('Arial', 12), width=30)
        phone_entry.grid(row=1, column=1, sticky="w", pady=6)

        # Врач (выбор)
        tk.Label(form, text="Врач *", font=('Arial', 12, 'bold'), bg="white").grid(row=2, column=0, sticky="w", pady=6)
        doctor_var = tk.StringVar()
        doctor_display = [f"{d['name']} — {d['room']}" for d in doctors]
        doctor_combo = ttk.Combobox(form, textvariable=doctor_var, values=doctor_display, state="readonly", width=28)
        doctor_combo.grid(row=2, column=1, sticky="w", pady=6)
        doctor_combo.current(0)

        # Услуга (выбор)
        tk.Label(form, text="Услуга", font=('Arial', 12, 'bold'), bg="white").grid(row=3, column=0, sticky="w", pady=6)
        service_var = tk.StringVar()
        services = ["—"] + self.db.get_services_list()
        service_combo = ttk.Combobox(form, textvariable=service_var, values=services, state="readonly", width=28)
        service_combo.grid(row=3, column=1, sticky="w", pady=6)
        service_combo.current(0)

        form.grid_columnconfigure(1, weight=1)

        def _get_selected_doctor():
            sel = doctor_combo.current()
            if sel < 0:
                return None
            return doctors[sel]

        def _save(invite: bool):
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Внимание", "Введите имя пациента")
                return
            phone = phone_var.get().strip()

            doctor = _get_selected_doctor()
            if not doctor:
                messagebox.showwarning("Внимание", "Выберите врача")
                return

            service = service_var.get().strip()
            if service == "—":
                service = ""

            apt_id = self.db.create_walk_in_appointment(name, phone, doctor["id"], service_name=service or None)

            # В очередь добавляем всегда, но статус зависит от занятости врача
            doc_status = self.db.get_doctor_status(doctor["id"]) or doctor.get("status") or "свободен"
            if invite and doc_status == "свободен":
                self.db.add_to_queue(apt_id, name, doctor["id"], doctor["room"], 'готов')
                self.announce_patient(name, doctor["room"])
            else:
                # если не приглашаем прямо сейчас — ставим ожидание/готовность по статусу врача
                q_status = 'готов' if doc_status == "свободен" else 'ожидание'
                self.db.add_to_queue(apt_id, name, doctor["id"], doctor["room"], q_status)
                if invite and q_status == 'готов':
                    self.announce_patient(name, doctor["room"])

            self.refresh_all()

            # НЕ закрываем окно — просто очистим имя/телефон
            name_var.set("")
            phone_var.set("")
            name_entry.focus_set()

        btns = tk.Frame(win, bg="white")
        btns.pack(fill="x", padx=20, pady=15)

        tk.Button(btns, text="Сохранить", bg="#2196F3", fg="white", font=('Arial', 12, 'bold'),
                  command=lambda: _save(invite=False), height=2, width=15).pack(side="left", padx=5)

        tk.Button(btns, text="Сохранить и пригласить", bg="#009688", fg="white", font=('Arial', 12, 'bold'),
                  command=lambda: _save(invite=True), height=2, width=22).pack(side="left", padx=5)

        tk.Button(btns, text="Закрыть", bg="#9E9E9E", fg="white", font=('Arial', 12, 'bold'),
                  command=win.destroy, height=2, width=10).pack(side="right", padx=5)

        name_entry.focus_set()

    def start_appointment(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите пациента из очереди")
            return

        try:
            queue_id = int(selected[0])
        except:
            messagebox.showerror("Ошибка", "Некорректный идентификатор очереди")
            return

        q = self.db.get_queue_item(queue_id)
        if not q:
            messagebox.showerror("Ошибка", "Запись очереди не найдена")
            return

        patient_name = q["patient_name"]
        status = q["status"]

        if status in ['готов', 'ожидание', 'вызван']:
            self.db.update_queue_status(queue_id, 'в_работе', 'started')
            self.db.update_doctor_status(q["doctor_id"], 'занят')
            self.refresh_all()
            messagebox.showinfo("Успешно", f"Начат приём: {patient_name}")
        else:
            messagebox.showwarning("Внимание", f"Невозможно начать приём. Статус: {status}")

    def finish_appointment(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите пациента из очереди")
            return

        try:
            queue_id = int(selected[0])
        except:
            messagebox.showerror("Ошибка", "Некорректный идентификатор очереди")
            return

        q = self.db.get_queue_item(queue_id)
        if not q:
            messagebox.showerror("Ошибка", "Запись очереди не найдена")
            return

        patient_name = q["patient_name"]
        status = q["status"]

        if status == 'в_работе':
            self.db.update_queue_status(queue_id, 'завершён', 'finished')
            self.db.update_doctor_status(q["doctor_id"], 'свободен')

            # важно: помечаем исходную запись завершённой, чтобы она исчезла из 'записей на сегодня'
            if q.get("appointment_id"):
                self.db.mark_appointment_completed(int(q["appointment_id"]))

            self.refresh_all()
            messagebox.showinfo("Успешно", f"Приём завершён: {patient_name}")
            self.check_waiting_patients(q["doctor_id"])
        else:
            messagebox.showwarning("Внимание", f"Невозможно завершить. Статус: {status}")

    def check_waiting_patients(self, doctor_id):
        conn = self.db.get_connection()
        waiting = conn.execute("""
            SELECT q.id, q.patient_name, q.room
            FROM queue q
            WHERE q.doctor_id = ? AND q.status = 'ожидание'
            ORDER BY q.called_at LIMIT 1
        """, (doctor_id,)).fetchone()
        conn.close()

        if waiting:
            self.db.update_queue_status(waiting['id'], 'готов')
            self.refresh_all()
            self.announce_patient(waiting['patient_name'], waiting['room'])

    def cancel_appointment_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Отмена записи")
        dialog.geometry("600x400")

        tk.Label(dialog, text="Поиск записи:", font=('Arial', 14, 'bold')).pack(pady=10)

        search_frame = tk.Frame(dialog)
        search_frame.pack(pady=10)

        search_entry = tk.Entry(search_frame, font=('Arial', 12), width=30)
        search_entry.pack(side='left', padx=5)

        results_tree = ttk.Treeview(dialog, columns=('Дата', 'Время', 'Пациент', 'Телефон', 'Врач'),
                                    show='headings', height=10)
        results_tree.heading('Дата', text='Дата')
        results_tree.heading('Время', text='Время')
        results_tree.heading('Пациент', text='Пациент')
        results_tree.heading('Телефон', text='Телефон')
        results_tree.heading('Врач', text='Врач')
        results_tree.pack(fill='both', expand=True, padx=10, pady=10)

        def search():
            search_text = search_entry.get()
            if search_text:
                results = self.db.search_appointments(search_text)
                for item in results_tree.get_children():
                    results_tree.delete(item)
                for apt in results:
                    results_tree.insert('', 'end', values=(
                        apt['appointment_date'], apt['appointment_time'], apt['patient_name'],
                        apt['phone'], apt['doctor_name']
                    ), tags=(apt['id'],))

        def cancel_selected():
            selected = results_tree.selection()
            if not selected:
                messagebox.showwarning("Внимание", "Выберите запись для отмены")
                return

            item = results_tree.item(selected[0])
            apt_id = item['tags'][0]
            patient_name = item['values'][2]

            if messagebox.askyesno("Подтверждение", f"Отменить запись для {patient_name}?"):
                self.db.cancel_appointment(apt_id)
                search()
                self.refresh_all()
                messagebox.showinfo("Успешно", "Запись отменена")

        tk.Button(search_frame, text="Найти", command=search, bg='#2196F3', fg='white',
                  font=('Arial', 11, 'bold')).pack(side='left', padx=5)

        tk.Button(dialog, text="Отменить выбранную запись", command=cancel_selected,
                  bg='#F44336', fg='white', font=('Arial', 12, 'bold')).pack(pady=10)

    def _conflict_resolution_dialog(self):
        """Диалог выбора действия при конфликте по времени. Возвращает: 'other'/'break'/'dayoff'/None."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Врач занят")
        dlg.geometry("520x220")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        tk.Label(dlg, text="Врач занят в выбранное время.", font=('Arial', 14, 'bold')).pack(pady=15)
        tk.Label(dlg, text="Выберите действие:", font=('Arial', 12)).pack(pady=5)

        result = {"val": None}

        btns = tk.Frame(dlg)
        btns.pack(pady=15)

        def setv(v):
            result["val"] = v
            dlg.destroy()

        ttk.Button(btns, text="Выбрать другого врача", style="Primary.TButton", command=lambda: setv("other")).grid(
            row=0, column=0, padx=8)
        ttk.Button(btns, text="Сделать перерыв", style="Warn.TButton", command=lambda: setv("break")).grid(row=0,
                                                                                                           column=1,
                                                                                                           padx=8)
        ttk.Button(btns, text="Сделать выходной", style="Danger.TButton", command=lambda: setv("dayoff")).grid(row=0,
                                                                                                               column=2,
                                                                                                               padx=8)

        ttk.Button(dlg, text="Отмена", command=lambda: setv(None)).pack(pady=5)

        dlg.wait_window()
        return result["val"]

    def edit_appointment_dialog(self):
        sel = self.appointments_tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите запись в таблице 'Записи на приём'.")
            return

        appointment_id = int(sel[0])
        conn = self.db.get_connection()
        row = conn.execute(
            """SELECT a.*, d.name as doctor_name
               FROM appointments a
               JOIN doctors d ON d.id = a.doctor_id
               WHERE a.id = ?""", (appointment_id,)
        ).fetchone()
        conn.close()
        if not row:
            messagebox.showerror("Ошибка", "Запись не найдена.")
            return
        apt = dict(row)

        dlg = tk.Toplevel(self.root)
        dlg.title("Редактирование записи")
        # ИСПРАВЛЕНО: увеличен размер окна редактирования
        dlg.geometry("820x700")
        dlg.minsize(760, 650)
        dlg.transient(self.root)
        dlg.grab_set()

        # Каркас с прокруткой для маленьких экранов
        canvas = tk.Canvas(dlg, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='white')

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        container = scrollable_frame
        container.grid_columnconfigure(1, weight=1)

        title = tk.Label(container, text="Изменить запись", font=('Arial', 16, 'bold'), bg='white')
        title.grid(row=0, column=0, columnspan=2, sticky='w', padx=12, pady=(12, 10))

        # Переменные
        date_var = tk.StringVar(value=apt.get("appointment_date", self.current_date))
        time_var = tk.StringVar(value=apt.get("appointment_time", "09:00"))
        name_var = tk.StringVar(value=apt.get("patient_name", ""))
        phone_var = tk.StringVar(value=apt.get("phone", ""))
        service_var = tk.StringVar(value=apt.get("service_name") or "")
        kind_var = tk.StringVar(value=apt.get("kind") or "patient")
        doctor_var = tk.StringVar(value=str(apt.get("doctor_id")))

        def row_label(r, text_):
            tk.Label(container, text=text_, font=('Arial', 12, 'bold'), bg='white').grid(row=r, column=0, sticky='w',
                                                                                         padx=(12, 10), pady=6)

        def row_entry(r, var):
            e = tk.Entry(container, textvariable=var, font=('Arial', 12), width=35)
            e.grid(row=r, column=1, sticky='ew', padx=12, pady=6)
            return e

        row_label(1, "Дата (ГГГГ-ММ-ДД)")
        row_entry(1, date_var)

        row_label(2, "Время (ЧЧ:ММ)")
        row_entry(2, time_var)

        row_label(3, "Тип записи")
        kind_combo = ttk.Combobox(container, textvariable=kind_var, state="readonly",
                                  values=["patient", "break", "dayoff"], width=32)
        kind_combo.grid(row=3, column=1, sticky='ew', padx=12, pady=6)

        row_label(4, "Пациент")
        name_entry = row_entry(4, name_var)

        row_label(5, "Телефон")
        phone_entry = row_entry(5, phone_var)

        row_label(6, "Услуга")
        services = self.db.get_services_list()
        service_combo = ttk.Combobox(container, textvariable=service_var, state="readonly", values=services, width=32)
        service_combo.grid(row=6, column=1, sticky='ew', padx=12, pady=6)

        row_label(7, "Врач")
        doctors = self.db.get_doctors()
        doctor_map = {str(d["id"]): d for d in doctors}
        doctor_values = [f'{d["id"]}: {d["name"]} (каб. {d["room"]})' for d in doctors]

        doctor_combo = ttk.Combobox(container, state="readonly", width=32)
        doctor_combo.grid(row=7, column=1, sticky='ew', padx=12, pady=6)

        def set_doctor_by_id(doc_id_str):
            # выставляем в комбобоксе красивую строку
            d = doctor_map.get(str(doc_id_str))
            if not d:
                return
            pretty = f'{d["id"]}: {d["name"]} (каб. {d["room"]})'
            doctor_combo.set(pretty)
            doctor_var.set(str(d["id"]))

        def refresh_doctor_options():
            # показываем всех, но помечаем занятых
            date_ = date_var.get().strip()
            time_ = time_var.get().strip()
            vals = []
            for d in doctors:
                busy = not self.db.is_doctor_available(d["id"], date_, time_, exclude_appointment_id=appointment_id)
                tag = " (занят)" if busy else ""
                vals.append(f'{d["id"]}: {d["name"]} (каб. {d["room"]}){tag}')
            doctor_combo["values"] = vals
            # восстановим выбранного
            set_doctor_by_id(doctor_var.get())

        def on_doctor_selected(event=None):
            v = doctor_combo.get()
            m = re.match(r'^(\d+):', v.strip())
            if m:
                doctor_var.set(m.group(1))

        doctor_combo.bind("<<ComboboxSelected>>", on_doctor_selected)

        def apply_kind_rules(*args):
            k = kind_var.get()
            if k in ("break", "dayoff"):
                # блокирующая запись
                label = "ПЕРЕРЫВ" if k == "break" else "ВЫХОДНОЙ"
                name_var.set(label)
                phone_var.set("")
                service_var.set("")
                name_entry.config(state="disabled")
                phone_entry.config(state="disabled")
                try:
                    service_combo.config(state="disabled")
                except Exception:
                    pass
            else:
                if name_entry.cget("state") == "disabled":
                    name_entry.config(state="normal")
                    phone_entry.config(state="normal")
                    try:
                        service_combo.config(state="readonly")
                    except Exception:
                        pass

        kind_var.trace_add("write", apply_kind_rules)
        apply_kind_rules()
        refresh_doctor_options()

        # обновлять список врачей при изменении даты/времени
        def on_time_date_change(*args):
            try:
                refresh_doctor_options()
            except Exception:
                pass

        date_var.trace_add("write", on_time_date_change)
        time_var.trace_add("write", on_time_date_change)

        # Кнопки
        actions = tk.Frame(container, bg='white')
        actions.grid(row=8, column=0, columnspan=2, sticky='ew', padx=12, pady=(18, 12))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        def save():
            date_ = date_var.get().strip()
            time_ = time_var.get().strip()
            k = kind_var.get().strip() or "patient"

            # валидация формата времени
            if not re.match(r"^\d{2}:\d{2}$", time_):
                messagebox.showerror("Ошибка", "Время должно быть в формате ЧЧ:ММ (например, 09:30).")
                return
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_):
                messagebox.showerror("Ошибка", "Дата должна быть в формате ГГГГ-ММ-ДД (например, 2026-02-05).")
                return

            doc_id = int(doctor_var.get())
            # если это пациент — проверяем занятость
            if k == "patient":
                if not self.db.is_doctor_available(doc_id, date_, time_, exclude_appointment_id=appointment_id):
                    choice = self._conflict_resolution_dialog()
                    if choice == "other":
                        return  # просто остаёмся в форме
                    if choice == "break":
                        kind_var.set("break")
                        apply_kind_rules()
                        return
                    if choice == "dayoff":
                        kind_var.set("dayoff")
                        apply_kind_rules()
                        return
                    return

            self.db.update_appointment(
                appointment_id,
                doctor_id=doc_id,
                date=date_,
                time_str=time_,
                patient_name=name_var.get().strip(),
                phone=phone_var.get().strip(),
                service_name=service_var.get().strip(),
                kind=k,
            )
            dlg.destroy()
            self.refresh_all()

        ttk.Button(actions, text="Сохранить", style="Ok.TButton", command=save).grid(row=0, column=0, sticky='ew',
                                                                                     padx=(0, 8))
        ttk.Button(actions, text="Закрыть", style="Primary.TButton", command=dlg.destroy).grid(row=0, column=1,
                                                                                               sticky='ew', padx=(8, 0))

        # применим текущую тему
        apply_theme_recursive(dlg, self.theme.t)

    def show_statistics(self):
        stats = self.db.get_stats()

        dialog = tk.Toplevel(self.root)
        dialog.title("Статистика")
        dialog.geometry("700x500")

        tk.Label(dialog, text="СТАТИСТИКА КЛИНИКИ", font=('Arial', 18, 'bold'),
                 fg='#1976D2').pack(pady=20)

        stats_frame = tk.LabelFrame(dialog, text="Общая статистика", font=('Arial', 14, 'bold'),
                                    padx=20, pady=20)
        stats_frame.pack(fill='both', padx=20, pady=10)

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

        for doc in stats['doctors']:
            tk.Label(doctors_frame, text=f"{doc['name']}: {doc['completed']} пациентов",
                     font=('Arial', 12)).pack(anchor='w', pady=3)

    def open_patient_display(self):
        if self.patient_display is None or not self.patient_display.winfo_exists():
            self.patient_display = PatientDisplay(self.root, self.db)
        else:
            self.patient_display.lift()

    def refresh_all(self):
        self.refresh_doctors()
        self.refresh_queue()
        self.refresh_appointments()
        if self.patient_display and self.patient_display.winfo_exists():
            self.patient_display.refresh()

    def refresh_doctors(self):
        for item in self.doctors_tree.get_children():
            self.doctors_tree.delete(item)

        doctors = self.db.get_doctors()
        for doc in doctors:
            self.doctors_tree.insert('', 'end', values=(doc['name'], doc['room'], doc['status']))

    def refresh_queue(self):
        # сохраняем выделение, чтобы оно не "сбрасывалось" при автообновлении
        selected = self.queue_tree.selection()
        selected_id = selected[0] if selected else None

        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

        queue = self.db.get_queue()
        for item in queue:
            self.queue_tree.insert('', 'end', iid=str(item['id']), values=(
                item['patient_name'],
                item.get('service_name') or '',
                item['doctor_name'],
                item['room'],
                item['status']
            ))

        # восстановим выделение, если элемент ещё существует
        if selected_id and self.queue_tree.exists(selected_id):
            self.queue_tree.selection_set(selected_id)
            self.queue_tree.focus(selected_id)

    def refresh_appointments(self):
        # сохраняем выделение, чтобы не пропадало при автообновлении
        selected = self.appointments_tree.selection()
        selected_id = selected[0] if selected else None

        for item in self.appointments_tree.get_children():
            self.appointments_tree.delete(item)

        apts = self.db.get_appointments(self.current_date)
        for apt in apts:
            self.appointments_tree.insert('', 'end', iid=str(apt['id']), values=(
                apt['appointment_time'],
                apt['patient_name'],
                apt['phone'],
                apt.get('service_name') or '',
                apt['doctor_name']
            ))

        if selected_id and self.appointments_tree.exists(selected_id):
            self.appointments_tree.selection_set(selected_id)
            self.appointments_tree.focus(selected_id)

    def announce_patient(self, patient_name, room):
        try:
            # На некоторых ПК Beep может быть отключён; MessageBeep обычно надёжнее.
            try:
                winsound.MessageBeep()
            except:
                pass
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

    def auto_check_appointments(self):
        while True:
            try:
                current_time = datetime.now()
                today = current_time.strftime('%Y-%m-%d')
                apts = self.db.get_appointments(today)

                for apt in apts:
                    apt_datetime = datetime.strptime(f"{apt['appointment_date']} {apt['appointment_time']}",
                                                     '%Y-%m-%d %H:%M')
                    time_diff = (current_time - apt_datetime).total_seconds()

                    if -60 <= time_diff <= 60:
                        conn = self.db.get_connection()
                        exists = conn.execute("SELECT id FROM queue WHERE appointment_id = ?",
                                              (apt['id'],)).fetchone()
                        conn.close()

                        if not exists:
                            doctor_status = self.db.get_doctor_status(apt['doctor_id'])

                            if doctor_status == 'свободен':
                                queue_id = self.db.add_to_queue(apt['id'], apt['patient_name'],
                                                                apt['doctor_id'], apt['room'], 'готов')
                                self.announce_patient(apt['patient_name'], apt['room'])
                            else:
                                self.db.add_to_queue(apt['id'], apt['patient_name'],
                                                     apt['doctor_id'], apt['room'], 'ожидание')

                self.root.after(0, self.refresh_all)
            except Exception as e:
                print(f"Ошибка автопроверки: {e}")

            time.sleep(CHECK_INTERVAL)


class PatientDisplay(tk.Toplevel):
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
        for widget in self.rooms_container.winfo_children():
            widget.destroy()

        doctors = self.db.get_doctors()
        queue = self.db.get_queue()

        for i, doctor in enumerate(doctors):
            row = i // 2
            col = i % 2
            self.create_doctor_card(doctor, queue, row, col)

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
