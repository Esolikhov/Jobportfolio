#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime
import uvicorn
import os
import threading

# ------------------------------
# DB mode:
# - If DATABASE_URL is set -> PostgreSQL (Supabase)
# - Else -> SQLite (local)
# ------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "dental_clinic.db")

USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")


def normalize_date_str(date_str: str) -> str:
    """
    Приводит дату к единому формату YYYY-MM-DD.
    Принимаем:
      - "2026-02-08"
      - "08.02.2026"
    Если формат не распознан — возвращаем как есть.
    """
    if not date_str:
        return date_str
    s = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s


app = FastAPI()

# Разрешаем запросы с Netlify/браузера
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


class AppointmentCreate(BaseModel):
    patient_name: str
    phone: str
    doctor_id: int
    appointment_date: str
    appointment_time: str
    service_name: str | None = None
    duration_hours: int | None = 1


# ==============================
# SQLite helpers (local)
# ==============================
import sqlite3


def ensure_schema_sqlite(conn: sqlite3.Connection) -> None:
    """Мягкая миграция SQLite БД без потери данных.
    Дополнительно создаёт таблицы, если их ещё нет (для полного backend).
    """
    cur = conn.cursor()

    # --- create tables (if missing) ---
    cur.execute(
        """CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            room TEXT DEFAULT '',
            status TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
        )"""
    )

    cur.execute(
        """CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            doctor_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            service_name TEXT,
            duration_hours INTEGER DEFAULT 1,
            status TEXT DEFAULT 'активна',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )"""
    )

    cur.execute(
        """CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            status TEXT DEFAULT 'ожидание',
            called_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (appointment_id) REFERENCES appointments(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )"""
    )

    cur.execute(
        """CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            duration_hours INTEGER DEFAULT 1,
            price REAL DEFAULT 0
        )"""
    )

    # --- mild migrations (columns) ---
    # appointments.service_name, duration_hours
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(appointments)").fetchall()]
        if "service_name" not in cols:
            cur.execute("ALTER TABLE appointments ADD COLUMN service_name TEXT")
        if "duration_hours" not in cols:
            cur.execute("ALTER TABLE appointments ADD COLUMN duration_hours INTEGER DEFAULT 1")
        if "status" not in cols:
            cur.execute("ALTER TABLE appointments ADD COLUMN status TEXT DEFAULT 'активна'")
    except Exception:
        pass

    # doctors.room/status/is_active
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(doctors)").fetchall()]
        if "room" not in cols:
            cur.execute("ALTER TABLE doctors ADD COLUMN room TEXT DEFAULT ''")
        if "status" not in cols:
            cur.execute("ALTER TABLE doctors ADD COLUMN status TEXT DEFAULT ''")
        if "is_active" not in cols:
            cur.execute("ALTER TABLE doctors ADD COLUMN is_active INTEGER DEFAULT 1")
    except Exception:
        pass

    # queue.called_at / queue.status
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(queue)").fetchall()]
        if "called_at" not in cols:
            cur.execute("ALTER TABLE queue ADD COLUMN called_at TEXT")
        if "status" not in cols:
            cur.execute("ALTER TABLE queue ADD COLUMN status TEXT DEFAULT 'ожидание'")
        if "appointment_id" not in cols:
            # крайне редкий случай: если таблица queue уже была создана иначе
            # здесь ничего не делаем, чтобы не потерять данные
            pass
    except Exception:
        pass

    conn.commit()


def get_db_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    ensure_schema_sqlite(conn)
    return conn


# ==============================
# Postgres helpers (Supabase)
# ==============================
_pg_pool = None


def _init_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        return
    # psycopg2-binary устанавливается через requirements.txt
    import psycopg2
    from psycopg2.pool import SimpleConnectionPool

    _pg_pool = SimpleConnectionPool(
        1, 5,
        dsn=DATABASE_URL,
        connect_timeout=10,
        sslmode=os.getenv("PGSSLMODE", "require"),
    )


def _pg_conn_key() -> str:
    # ключ нужен, чтобы psycopg2 pool корректно возвращал соединение именно этому потоку/воркеру
    return f"{os.getpid()}-{threading.get_ident()}"


def _pg_getconn():
    _init_pg_pool()
    key = _pg_conn_key()
    conn = _pg_pool.getconn(key)
    return conn, key


def _pg_putconn(conn, key: str):
    # сначала пробуем вернуть по ключу; если по какой-то причине пул его не знает — пробуем без ключа
    try:
        _pg_pool.putconn(conn, key)
    except Exception:
        try:
            _pg_pool.putconn(conn)
        except Exception:
            pass


def ensure_schema_pg():
    """Добавляет отсутствующие таблицы/колонки (без потери данных).
    Примечание: требует прав на DDL; если прав нет, просто продолжим работу.
    """
    if not USE_POSTGRES:
        return
    _init_pg_pool()
    conn, _key = _pg_getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Проверка doctors
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.doctors (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    room TEXT DEFAULT '',
                    status TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            # Миграция колонок
            try:
                cur.execute("ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS room TEXT DEFAULT ''")
                cur.execute("ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS status TEXT DEFAULT ''")
                cur.execute("ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
            except Exception:
                pass

            # appointments
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.appointments (
                    id SERIAL PRIMARY KEY,
                    patient_name TEXT NOT NULL,
                    phone TEXT DEFAULT '',
                    doctor_id INTEGER NOT NULL,
                    appointment_date TEXT NOT NULL,
                    appointment_time TEXT NOT NULL,
                    service_name TEXT,
                    duration_hours INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'активна',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (doctor_id) REFERENCES public.doctors(id)
                )
            """)
            try:
                cur.execute("ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS service_name TEXT")
                cur.execute("ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS duration_hours INTEGER DEFAULT 1")
                cur.execute("ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'активна'")
            except Exception:
                pass

            # queue
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.queue (
                    id SERIAL PRIMARY KEY,
                    appointment_id INTEGER NOT NULL,
                    doctor_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'ожидание',
                    called_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (appointment_id) REFERENCES public.appointments(id),
                    FOREIGN KEY (doctor_id) REFERENCES public.doctors(id)
                )
            """)
            try:
                cur.execute("ALTER TABLE public.queue ADD COLUMN IF NOT EXISTS called_at TIMESTAMPTZ")
                cur.execute("ALTER TABLE public.queue ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ожидание'")
            except Exception:
                pass

            # services
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.services (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    duration_hours INTEGER DEFAULT 1,
                    price NUMERIC DEFAULT 0
                )
            """)

    except Exception as e:
        print(f"Ошибка при инициализации схемы PostgreSQL: {e}")
    finally:
        _pg_putconn(conn, _key)


# Инициализируем схему при старте
ensure_schema_pg()


def pg_query_all(sql: str, params: tuple = ()):
    """Выполняет SELECT, возвращает список dict."""
    conn, key = _pg_getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
    finally:
        _pg_putconn(conn, key)


def pg_query_one(sql: str, params: tuple = ()):
    """Выполняет SELECT, возвращает один dict или None."""
    conn, key = _pg_getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description] if cur.description else []
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None
    finally:
        _pg_putconn(conn, key)


def pg_execute(sql: str, params: tuple = (), returning_id: bool = False):
    """INSERT / UPDATE / DELETE. Если returning_id=True, возвращает id."""
    conn, key = _pg_getconn()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            if returning_id:
                cur.execute(sql + " RETURNING id", params)
                row = cur.fetchone()
                conn.commit()
                return row[0] if row else None
            else:
                cur.execute(sql, params)
                conn.commit()
                return None
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        _pg_putconn(conn, key)


# ==============================
# API endpoints
# ==============================

@app.get("/api/doctors")
def get_doctors():
    """Возвращает список всех врачей"""
    if USE_POSTGRES:
        doctors = pg_query_all("SELECT * FROM public.doctors WHERE is_active = TRUE ORDER BY id")
        return doctors

    conn = get_db_sqlite()
    doctors = conn.execute("SELECT * FROM doctors WHERE is_active = 1 ORDER BY id").fetchall()
    conn.close()
    return [dict(row) for row in doctors]


@app.get("/api/services")
def get_services():
    """Возвращает список всех услуг"""
    if USE_POSTGRES:
        services = pg_query_all("SELECT * FROM public.services ORDER BY id")
        return services

    conn = get_db_sqlite()
    services = conn.execute("SELECT * FROM services ORDER BY id").fetchall()
    conn.close()
    return [dict(row) for row in services]


@app.post("/api/services")
def create_service(data: dict):
    """Создание новой услуги"""
    name = data.get("name", "").strip()
    duration_hours = data.get("duration_hours", 1)
    price = data.get("price", 0)

    if not name:
        raise HTTPException(status_code=400, detail="Название услуги обязательно")

    if USE_POSTGRES:
        new_id = pg_execute(
            "INSERT INTO public.services (name, duration_hours, price) VALUES (%s, %s, %s)",
            (name, duration_hours, price),
            returning_id=True
        )
        return {"success": True, "id": int(new_id)}

    conn = get_db_sqlite()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO services (name, duration_hours, price) VALUES (?, ?, ?)",
        (name, duration_hours, price)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"success": True, "id": int(new_id)}


@app.get("/api/available-slots")
def get_available_slots(date: str, doctor_id: int = None):
    """Возвращает доступные слоты времени"""
    # Генерируем слоты с 8:00 до 18:00 каждые 30 минут
    slots = []
    h, m = 8, 0
    while True:
        slots.append(f"{h:02d}:{m:02d}")
        m += 30
        if m >= 60:
            h += 1
            m -= 60
        if h > 18 or (h == 18 and m > 0):
            break

    # Фильтруем занятые слоты
    if USE_POSTGRES:
        if doctor_id:
            occupied = pg_query_all(
                "SELECT appointment_time FROM public.appointments WHERE doctor_id = %s AND appointment_date = %s AND status = 'активна'",
                (doctor_id, date)
            )
        else:
            occupied = pg_query_all(
                "SELECT appointment_time FROM public.appointments WHERE appointment_date = %s AND status = 'активна'",
                (date,)
            )
        occupied_times = {row['appointment_time'] for row in occupied}
    else:
        conn = get_db_sqlite()
        if doctor_id:
            occupied = conn.execute(
                "SELECT appointment_time FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND status = 'активна'",
                (doctor_id, date)
            ).fetchall()
        else:
            occupied = conn.execute(
                "SELECT appointment_time FROM appointments WHERE appointment_date = ? AND status = 'активна'",
                (date,)
            ).fetchall()
        occupied_times = {row['appointment_time'] for row in occupied}
        conn.close()

    available_slots = [slot for slot in slots if slot not in occupied_times]
    return available_slots


@app.post("/api/appointments")
def create_appointment(appointment: AppointmentCreate):
    """Создание новой записи"""
    # Проверка занятости слота
    if USE_POSTGRES:
        existing = pg_query_one(
            "SELECT id FROM public.appointments WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s AND status = 'активна'",
            (appointment.doctor_id, appointment.appointment_date, appointment.appointment_time)
        )
        if existing:
            raise HTTPException(status_code=400, detail="Время занято")

        new_id = pg_execute(
            """INSERT INTO public.appointments
                (patient_name, phone, doctor_id, appointment_date, appointment_time, service_name, duration_hours, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'активна')""",
            (
                appointment.patient_name,
                appointment.phone,
                appointment.doctor_id,
                appointment.appointment_date,
                appointment.appointment_time,
                appointment.service_name,
                appointment.duration_hours or 1,
            ),
            returning_id=True,
        )
        return {"success": True, "id": int(new_id)}

    conn = get_db_sqlite()
    cursor = conn.cursor()
    existing = cursor.execute(
        "SELECT id FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ? AND status = 'активна'",
        (appointment.doctor_id, appointment.appointment_date, appointment.appointment_time),
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Время занято")

    cursor.execute(
        """INSERT INTO appointments
            (patient_name, phone, doctor_id, appointment_date, appointment_time, service_name, duration_hours, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'активна')""",
        (
            appointment.patient_name,
            appointment.phone,
            appointment.doctor_id,
            appointment.appointment_date,
            appointment.appointment_time,
            appointment.service_name,
            appointment.duration_hours or 1,
        ),
    )
    conn.commit()
    apt_id = cursor.lastrowid
    conn.close()
    return {"success": True, "id": apt_id}


@app.put("/api/appointments/{apt_id}")
def update_appointment(apt_id: int, data: dict):
    """Обновление записи (перенос/смена врача/времени/даты) — нужно клиенту.
    Ожидаемые поля: doctor_id, appointment_date, appointment_time, (опционально phone, patient_name, service_name, status)
    """
    allowed = {"doctor_id", "appointment_date", "appointment_time", "patient_name", "phone", "service_name", "status", "duration_hours"}
    fields = {k: v for k, v in (data or {}).items() if k in allowed}

    if not fields:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    # проверим конфликт слота, если меняют doctor_id/date/time
    new_doctor = fields.get("doctor_id")
    new_date = fields.get("appointment_date")
    new_time = fields.get("appointment_time")

    if USE_POSTGRES:
        # получаем текущую запись
        current = pg_query_one("SELECT * FROM public.appointments WHERE id = %s", (apt_id,))
        if not current:
            raise HTTPException(status_code=404, detail="Запись не найдена")

        doctor_id = new_doctor if new_doctor is not None else current["doctor_id"]
        ap_date = new_date if new_date is not None else current["appointment_date"]
        ap_time = new_time if new_time is not None else current["appointment_time"]

        # конфликт
        existing = pg_query_one(
            """SELECT id FROM public.appointments
               WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s
                 AND status = 'активна' AND id <> %s
               LIMIT 1""",
            (doctor_id, ap_date, ap_time, apt_id),
        )
        if existing:
            raise HTTPException(status_code=400, detail="Время занято")

        set_parts = []
        params = []
        for k, v in fields.items():
            set_parts.append(f"{k} = %s")
            params.append(v)
        params.append(apt_id)
        pg_execute(f"UPDATE public.appointments SET {', '.join(set_parts)} WHERE id = %s", tuple(params))
        return {"success": True}

    conn = get_db_sqlite()
    cur = conn.cursor()
    current = cur.execute("SELECT * FROM appointments WHERE id = ?", (apt_id,)).fetchone()
    if not current:
        conn.close()
        raise HTTPException(status_code=404, detail="Запись не найдена")

    doctor_id = new_doctor if new_doctor is not None else current["doctor_id"]
    ap_date = new_date if new_date is not None else current["appointment_date"]
    ap_time = new_time if new_time is not None else current["appointment_time"]

    existing = cur.execute(
        """SELECT id FROM appointments
           WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
             AND status = 'активна' AND id <> ? LIMIT 1""",
        (doctor_id, ap_date, ap_time, apt_id),
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Время занято")

    set_parts = []
    params = []
    for k, v in fields.items():
        set_parts.append(f"{k} = ?")
        params.append(v)
    params.append(apt_id)
    cur.execute(f"UPDATE appointments SET {', '.join(set_parts)} WHERE id = ?", tuple(params))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/appointments/search")
def search_appointments(patient_name: str = ""):
    """Поиск записей по ФИО/имени пациента — используется клиентом."""
    q = (patient_name or "").strip()
    if q == "":
        # возвращать всё не будем (это тяжело); но для совместимости вернём пусто
        return []

    if USE_POSTGRES:
        return pg_query_all(
            """SELECT a.*, d.name as doctor_name, d.room
               FROM public.appointments a
               LEFT JOIN public.doctors d ON a.doctor_id = d.id
               WHERE LOWER(a.patient_name) LIKE LOWER(%s)
               ORDER BY a.appointment_date DESC, a.appointment_time DESC
               LIMIT 200""",
            (f"%{q}%",),
        )

    conn = get_db_sqlite()
    rows = conn.execute(
        """SELECT a.*, d.name as doctor_name, d.room
           FROM appointments a
           LEFT JOIN doctors d ON a.doctor_id = d.id
           WHERE LOWER(a.patient_name) LIKE ?
           ORDER BY a.appointment_date DESC, a.appointment_time DESC
           LIMIT 200""",
        (f"%{q.lower()}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/appointments/today")
def get_today_appointments(date: str = None):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    if USE_POSTGRES:
        return pg_query_all(
            """SELECT a.*, d.name as doctor_name, d.room
               FROM public.appointments a
               JOIN public.doctors d ON a.doctor_id = d.id
               WHERE a.appointment_date = %s AND a.status = 'активна'
               ORDER BY a.appointment_time""",
            (date,),
        )

    conn = get_db_sqlite()
    apts = conn.execute(
        """SELECT a.*, d.name as doctor_name, d.room
           FROM appointments a
           JOIN doctors d ON a.doctor_id = d.id
           WHERE a.appointment_date = ? AND a.status = 'активна'
           ORDER BY a.appointment_time""",
        (date,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in apts]


@app.get("/api/queue")
def get_queue():
    """Очередь — клиенту нужны: id, status, doctor_id, doctor_name, room, patient_name, phone, service_name, appointment_id, called_at, duration_hours."""
    if USE_POSTGRES:
        return pg_query_all(
            """SELECT q.*,
                      d.name as doctor_name,
                      d.room as room,
                      a.patient_name as patient_name,
                      a.phone as phone,
                      a.service_name as service_name,
                      a.duration_hours as duration_hours,
                      a.appointment_date as appointment_date,
                      a.appointment_time as appointment_time
               FROM public.queue q
               JOIN public.doctors d ON q.doctor_id = d.id
               LEFT JOIN public.appointments a ON q.appointment_id = a.id
               WHERE q.status NOT IN ('завершён', 'не_пришёл')
               ORDER BY q.called_at NULLS LAST, q.id"""
        )

    conn = get_db_sqlite()
    queue = conn.execute(
        """SELECT q.*,
                  d.name as doctor_name,
                  d.room as room,
                  a.patient_name as patient_name,
                  a.phone as phone,
                  a.service_name as service_name,
                  a.duration_hours as duration_hours,
                  a.appointment_date as appointment_date,
                  a.appointment_time as appointment_time
           FROM queue q
           JOIN doctors d ON q.doctor_id = d.id
           LEFT JOIN appointments a ON q.appointment_id = a.id
           WHERE q.status NOT IN ('завершён', 'не_пришёл')
           ORDER BY q.called_at NULLS LAST, q.id"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in queue]


@app.post("/api/queue")
def add_to_queue(data: dict):
    """Добавить пациента в очередь по appointment_id"""
    appointment_id = data.get("appointment_id")
    if not appointment_id:
        raise HTTPException(status_code=400, detail="appointment_id required")

    if USE_POSTGRES:
        apt = pg_query_one("SELECT * FROM public.appointments WHERE id = %s", (appointment_id,))
        if not apt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        doctor_id = apt.get("doctor_id")
        patient_name = apt.get("patient_name") or apt.get("name") or ""
        if not patient_name:
            raise HTTPException(status_code=422, detail="patient_name missing in appointment")

        # room is required (NOT NULL) in queue table
        room = apt.get("room")
        if not room and doctor_id is not None:
            doc = pg_query_one("SELECT room FROM public.doctors WHERE id = %s", (doctor_id,))
            room = (doc.get("room") if doc else None)

        if not room:
            room = "-"  # безопасное значение, чтобы не нарушать NOT NULL

        # Проверяем, не в очереди ли уже
        exists = pg_query_one(
            "SELECT id FROM public.queue WHERE appointment_id = %s AND status NOT IN ('завершён', 'не_пришёл', 'отменён')",
            (appointment_id,),
        )
        if exists:
            return {"ok": True, "queue_id": exists["id"], "message": "Already in queue"}

        sql = "INSERT INTO public.queue (appointment_id, patient_name, doctor_id, room, status) VALUES (%s, %s, %s, %s, 'ожидание')"
        params = (appointment_id, patient_name, doctor_id, room)
        new_id = pg_execute(sql, params, returning_id=True)

        return {"ok": True, "id": new_id, "appointment_id": appointment_id, "patient_name": patient_name, "doctor_id": doctor_id, "room": room, "status": "ожидание"}

    conn = get_db_sqlite()
    cur = conn.cursor()
    apt = cur.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
    if not apt:
        conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    doctor_id = apt["doctor_id"]
    room = apt.get("room", "")

    exists = cur.execute(
        "SELECT id FROM queue WHERE appointment_id = ? AND status NOT IN ('завершён', 'не_пришёл')",
        (appointment_id,)
    ).fetchone()
    if exists:
        conn.close()
        raise HTTPException(status_code=400, detail="Уже в очереди")

    insert_cols = ["appointment_id", "doctor_id", "status"]
    insert_vals = [appointment_id, doctor_id, "ожидание"]

    cols = [r[1] for r in cur.execute("PRAGMA table_info(queue)").fetchall()]
    if "room" in cols:
        insert_cols.append("room")
        insert_vals.append(room)

    qmarks = ", ".join(["?"] * len(insert_cols))
    cur.execute(f"INSERT INTO queue ({', '.join(insert_cols)}) VALUES ({qmarks})", tuple(insert_vals))
    conn.commit()
    new_id = cur.lastrowid

    # Изменить статус записи на "в_работе"
    cur.execute("UPDATE appointments SET status = 'в_работе' WHERE id = ?", (appointment_id,))
    conn.commit()
    conn.close()

    return {"success": True, "id": int(new_id)}


@app.put("/api/queue/{queue_id}/status")
def update_queue_status(queue_id: int, data: dict):
    """Обновить статус элемента очереди. Клиент шлёт {"status": "..."}"""
    status = (data or {}).get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status required")

    # если статус меняется на "вызван/в_работе" и called_at пустой — ставим время
    now_iso = datetime.now().isoformat(timespec="seconds")

    if USE_POSTGRES:
        row = pg_query_one("SELECT id, called_at, doctor_id, appointment_id FROM public.queue WHERE id = %s",
                           (queue_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Queue item not found")

        doctor_id = row.get("doctor_id")
        appointment_id = row.get("appointment_id")

        if row.get("called_at") is None:
            pg_execute("UPDATE public.queue SET status = %s, called_at = now() WHERE id = %s", (status, queue_id))
        else:
            pg_execute("UPDATE public.queue SET status = %s WHERE id = %s", (status, queue_id))

        # Изменение статуса записи
        if status == "завершён":
            pg_execute("UPDATE public.appointments SET status = 'завершена' WHERE id = %s", (appointment_id,))
        elif status == "не_пришёл":
            pg_execute("UPDATE public.appointments SET status = 'не_пришёл' WHERE id = %s", (appointment_id,))

        # Изменение статуса врача
        if status in ("готов", "в_работе"):
            pg_execute("UPDATE public.doctors SET status = 'занят' WHERE id = %s", (doctor_id,))
        elif status in ("завершён", "не_пришёл"):
            active = pg_query_one(
                "SELECT COUNT(*)::int as cnt FROM public.queue WHERE doctor_id = %s AND status IN ('ожидание', 'готов', 'в_работе')",
                (doctor_id,)
            )
            if active and active.get("cnt", 0) == 0:
                # Проверяем текущий статус врача
                doctor = pg_query_one("SELECT status FROM public.doctors WHERE id = %s", (doctor_id,))
                if doctor and doctor.get("status") not in ("выходной", "перерыв"):
                    pg_execute("UPDATE public.doctors SET status = 'свободен' WHERE id = %s", (doctor_id,))

        return {"success": True}

    conn = get_db_sqlite()
    cur = conn.cursor()
    row = cur.execute("SELECT id, called_at, doctor_id, appointment_id FROM queue WHERE id = ?", (queue_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Queue item not found")

    doctor_id = row["doctor_id"]
    appointment_id = row["appointment_id"]

    if row["called_at"] is None:
        cur.execute("UPDATE queue SET status = ?, called_at = ? WHERE id = ?", (status, now_iso, queue_id))
    else:
        cur.execute("UPDATE queue SET status = ? WHERE id = ?", (status, queue_id))

    # Изменение статуса записи
    if status == "завершён":
        cur.execute("UPDATE appointments SET status = 'завершена' WHERE id = ?", (appointment_id,))
    elif status == "не_пришёл":
        cur.execute("UPDATE appointments SET status = 'не_пришёл' WHERE id = ?", (appointment_id,))

    # Изменение статуса врача
    if status in ("готов", "в_работе"):
        cur.execute("UPDATE doctors SET status = 'занят' WHERE id = ?", (doctor_id,))
    elif status in ("завершён", "не_пришёл"):
        active = cur.execute(
            "SELECT COUNT(*) as cnt FROM queue WHERE doctor_id = ? AND status IN ('ожидание', 'готов', 'в_работе')",
            (doctor_id,)
        ).fetchone()
        if active and active["cnt"] == 0:
            # Проверяем текущий статус врача
            doctor = cur.execute("SELECT status FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
            if doctor and doctor["status"] not in ("выходной", "перерыв"):
                cur.execute("UPDATE doctors SET status = 'свободен' WHERE id = ?", (doctor_id,))

    conn.commit()
    conn.close()
    return {"success": True}


@app.put("/api/doctors/{doctor_id}/status")
def update_doctor_status(doctor_id: int, data: dict):
    status = data.get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status required")

    if USE_POSTGRES:
        pg_execute("UPDATE public.doctors SET status = %s WHERE id = %s", (status, doctor_id))
        return {"success": True}

    conn = get_db_sqlite()
    conn.execute("UPDATE doctors SET status = ? WHERE id = ?", (status, doctor_id))
    conn.commit()
    conn.close()
    return {"success": True}


@app.put("/api/appointments/{apt_id}/cancel")
def cancel_appointment(apt_id: int):
    if USE_POSTGRES:
        # Получаем doctor_id из очереди перед удалением
        queue_item = pg_query_one("SELECT doctor_id FROM public.queue WHERE appointment_id = %s", (apt_id,))

        pg_execute("UPDATE public.appointments SET status = 'отменена' WHERE id = %s", (apt_id,))
        pg_execute("DELETE FROM public.queue WHERE appointment_id = %s", (apt_id,))

        # Освобождаем врача если у него нет активных пациентов
        if queue_item:
            doctor_id = queue_item.get("doctor_id")
            active = pg_query_one(
                "SELECT COUNT(*)::int as cnt FROM public.queue WHERE doctor_id = %s AND status IN ('ожидание', 'готов', 'в_работе')",
                (doctor_id,)
            )
            if active and active.get("cnt", 0) == 0:
                doctor = pg_query_one("SELECT status FROM public.doctors WHERE id = %s", (doctor_id,))
                if doctor and doctor.get("status") not in ("выходной", "перерыв"):
                    pg_execute("UPDATE public.doctors SET status = 'свободен' WHERE id = %s", (doctor_id,))

        return {"success": True}

    conn = get_db_sqlite()
    cur = conn.cursor()

    # Получаем doctor_id из очереди перед удалением
    queue_item = cur.execute("SELECT doctor_id FROM queue WHERE appointment_id = ?", (apt_id,)).fetchone()

    cur.execute("UPDATE appointments SET status = 'отменена' WHERE id = ?", (apt_id,))
    cur.execute("DELETE FROM queue WHERE appointment_id = ?", (apt_id,))

    # Освобождаем врача если у него нет активных пациентов
    if queue_item:
        doctor_id = queue_item["doctor_id"]
        active = cur.execute(
            "SELECT COUNT(*) as cnt FROM queue WHERE doctor_id = ? AND status IN ('ожидание', 'готов', 'в_работе')",
            (doctor_id,)
        ).fetchone()
        if active and active["cnt"] == 0:
            doctor = cur.execute("SELECT status FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
            if doctor and doctor["status"] not in ("выходной", "перерыв"):
                cur.execute("UPDATE doctors SET status = 'свободен' WHERE id = ?", (doctor_id,))

    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/stats")
def get_stats():
    if USE_POSTGRES:
        total = pg_query_one("SELECT COUNT(*)::int as cnt FROM public.appointments")["cnt"]
        active = pg_query_one("SELECT COUNT(*)::int as cnt FROM public.appointments WHERE status = 'активна'")["cnt"]
        cancelled = pg_query_one("SELECT COUNT(*)::int as cnt FROM public.appointments WHERE status = 'отменена'")[
            "cnt"]
        completed = pg_query_one("SELECT COUNT(*)::int as cnt FROM public.queue WHERE status = 'завершён'")["cnt"]
        doctors_stats = pg_query_all(
            """SELECT d.name, COUNT(q.id)::int as completed_count
               FROM public.doctors d
               LEFT JOIN public.queue q
                 ON d.id = q.doctor_id AND q.status = 'завершён'
               GROUP BY d.id, d.name
               ORDER BY d.id"""
        )
        return {
            "total": total,
            "active": active,
            "cancelled": cancelled,
            "completed": completed,
            "doctors": doctors_stats,
        }

    conn = get_db_sqlite()
    total = conn.execute("SELECT COUNT(*) as cnt FROM appointments").fetchone()["cnt"]
    active = conn.execute("SELECT COUNT(*) as cnt FROM appointments WHERE status = 'активна'").fetchone()["cnt"]
    cancelled = conn.execute("SELECT COUNT(*) as cnt FROM appointments WHERE status = 'отменена'").fetchone()["cnt"]
    completed = conn.execute("SELECT COUNT(*) as cnt FROM queue WHERE status = 'завершён'").fetchone()["cnt"]
    doctors_stats = conn.execute(
        "SELECT d.name, COUNT(q.id) as completed_count FROM doctors d LEFT JOIN queue q ON d.id = q.doctor_id AND q.status = 'завершён' GROUP BY d.id, d.name"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "active": active,
        "cancelled": cancelled,
        "completed": completed,
        "doctors": [dict(row) for row in doctors_stats],
    }


# Чтобы backend-url мог отдавать фронт-страницу и статику (если хочешь)
if os.path.isdir("website"):
    # /style.css, /script.js и т.п.
    app.mount("/", StaticFiles(directory="website", html=True), name="website")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
