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
            status TEXT DEFAULT 'доступен',
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

    # --- mild migrations (columns) ---
    # appointments.service_name
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(appointments)").fetchall()]
        if "service_name" not in cols:
            cur.execute("ALTER TABLE appointments ADD COLUMN service_name TEXT")
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
            cur.execute("ALTER TABLE doctors ADD COLUMN status TEXT DEFAULT 'доступен'")
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
            _pg_putconn(conn, _key)
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
            try:
                # tables (idempotent)
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS public.doctors (
                        id serial PRIMARY KEY,
                        name text NOT NULL,
                        room text DEFAULT '',
                        status text DEFAULT 'доступен',
                        is_active int DEFAULT 1
                    )"""
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS public.appointments (
                        id serial PRIMARY KEY,
                        patient_name text NOT NULL,
                        phone text DEFAULT '',
                        doctor_id int NOT NULL,
                        appointment_date text NOT NULL,
                        appointment_time text NOT NULL,
                        service_name text,
                        status text DEFAULT 'активна',
                        created_at timestamptz DEFAULT now()
                    )"""
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS public.queue (
                        id serial PRIMARY KEY,
                        appointment_id int NOT NULL,
                        doctor_id int NOT NULL,
                        status text DEFAULT 'ожидание',
                        called_at timestamptz,
                        created_at timestamptz DEFAULT now()
                    )"""
                )
            except Exception:
                # нет прав на CREATE TABLE — не ломаем приложение
                pass

            # appointments.service_name (если нет в create_db.py)
            try:
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name='appointments'
                      AND column_name='service_name'
                    """
                )
                exists = cur.fetchone() is not None
                if not exists:
                    cur.execute("ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS service_name text")
            except Exception:
                pass

            # doctors room/status/is_active
            for col, ddl in [
                ("room", "ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS room text DEFAULT ''"),
                ("status", "ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS status text DEFAULT 'доступен'"),
                ("is_active", "ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS is_active int DEFAULT 1"),
            ]:
                try:
                    cur.execute(
                        """
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema='public'
                          AND table_name='doctors'
                          AND column_name=%s
                        """,
                        (col,),
                    )
                    if cur.fetchone() is None:
                        cur.execute(ddl)
                except Exception:
                    pass

            # queue columns
            for col, ddl in [
                ("called_at", "ALTER TABLE public.queue ADD COLUMN IF NOT EXISTS called_at timestamptz"),
                ("status", "ALTER TABLE public.queue ADD COLUMN IF NOT EXISTS status text DEFAULT 'ожидание'"),
            ]:
                try:
                    cur.execute(
                        """
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema='public'
                          AND table_name='queue'
                          AND column_name=%s
                        """,
                        (col,),
                    )
                    if cur.fetchone() is None:
                        cur.execute(ddl)
                except Exception:
                    pass
    finally:
        _pg_putconn(conn, _key)

def pg_query_all(sql: str, params=None):
    from psycopg2.extras import RealDictCursor
    _init_pg_pool()
    ensure_schema_pg()
    conn, _key = _pg_getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        _pg_putconn(conn, _key)

def pg_query_one(sql: str, params=None):
    from psycopg2.extras import RealDictCursor
    _init_pg_pool()
    ensure_schema_pg()
    conn, _key = _pg_getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    finally:
        _pg_putconn(conn, _key)

def pg_execute(sql: str, params=None, returning_id: bool = False):
    _init_pg_pool()
    ensure_schema_pg()
    conn, _key = _pg_getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            new_id = None
            if returning_id:
                new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    finally:
        _pg_putconn(conn, _key)


# Cache for Postgres table columns (for compatibility with existing schemas)
_pg_cols_cache = {}

def pg_table_columns(table_name: str):
    """Return list of column metadata dicts for public.<table_name>."""
    key = table_name.lower()
    if key in _pg_cols_cache:
        return _pg_cols_cache[key]
    rows = pg_query_all(
        """SELECT column_name, is_nullable, column_default
             FROM information_schema.columns
             WHERE table_schema='public' AND table_name=%s
             ORDER BY ordinal_position""",
        (key,),
    )
    _pg_cols_cache[key] = rows or []
    return _pg_cols_cache[key]



# ==============================
# API
# ==============================
@app.get("/")
def read_root():
    # Чтобы backend-url мог показывать сайт (опционально)
    if os.path.exists("website/index.html"):
        return FileResponse("website/index.html")
    return {"status": "ok", "service": "dental-backend", "db": "postgres" if USE_POSTGRES else "sqlite"}


@app.get("/api/doctors")
def get_doctors():
    if USE_POSTGRES:
        return pg_query_all("SELECT * FROM public.doctors WHERE is_active = 1 ORDER BY id")
    conn = get_db_sqlite()
    doctors = conn.execute("SELECT * FROM doctors WHERE is_active = 1").fetchall()
    conn.close()
    return [dict(row) for row in doctors]


@app.get("/api/available-slots")
def get_available_slots(doctor_id: int, date: str):
    """ВАЖНО: клиент ждёт список строк времени (['08:00','08:30',...]),
    а не список объектов. Поэтому возвращаем именно list[str].
    """
    slots = []
    if USE_POSTGRES:
        for hour in range(8, 17):
            for minute in (0, 30):
                time_str = f"{hour:02d}:{minute:02d}"
                existing = pg_query_one(
                    "SELECT id FROM public.appointments WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s AND status = 'активна' LIMIT 1",
                    (doctor_id, date, time_str),
                )
                if existing is None:
                    slots.append(time_str)
        return slots

    conn = get_db_sqlite()
    for hour in range(8, 17):
        for minute in (0, 30):
            time_str = f"{hour:02d}:{minute:02d}"
            existing = conn.execute(
                "SELECT id FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ? AND status = 'активна'",
                (doctor_id, date, time_str),
            ).fetchone()
            if existing is None:
                slots.append(time_str)
    conn.close()
    return slots


@app.post("/api/appointments")
def create_appointment(appointment: AppointmentCreate):
    if USE_POSTGRES:
        existing = pg_query_one(
            "SELECT id FROM public.appointments WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s AND status = 'активна' LIMIT 1",
            (appointment.doctor_id, appointment.appointment_date, appointment.appointment_time),
        )
        if existing:
            raise HTTPException(status_code=400, detail="Время занято")

        new_id = pg_execute(
            """INSERT INTO public.appointments
                (patient_name, phone, doctor_id, appointment_date, appointment_time, service_name, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'активна')
               RETURNING id""",
            (
                appointment.patient_name,
                appointment.phone,
                appointment.doctor_id,
                appointment.appointment_date,
                appointment.appointment_time,
                appointment.service_name,
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
            (patient_name, phone, doctor_id, appointment_date, appointment_time, service_name, status)
           VALUES (?, ?, ?, ?, ?, ?, 'активна')""",
        (
            appointment.patient_name,
            appointment.phone,
            appointment.doctor_id,
            appointment.appointment_date,
            appointment.appointment_time,
            appointment.service_name,
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
    allowed = {"doctor_id", "appointment_date", "appointment_time", "patient_name", "phone", "service_name", "status"}
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
               WHERE a.appointment_date = %s
               ORDER BY a.appointment_time""",
            (date,),
        )

    conn = get_db_sqlite()
    apts = conn.execute(
        """SELECT a.*, d.name as doctor_name, d.room
           FROM appointments a
           JOIN doctors d ON a.doctor_id = d.id
           WHERE a.appointment_date = ?
           ORDER BY a.appointment_time""",
        (date,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in apts]


@app.get("/api/queue")
def get_queue():
    """Очередь — клиенту нужны: id, status, doctor_id, doctor_name, room, patient_name, phone, service_name, appointment_id, called_at."""
    if USE_POSTGRES:
        return pg_query_all(
            """SELECT q.*,
                      d.name as doctor_name,
                      d.room as room,
                      a.patient_name as patient_name,
                      a.phone as phone,
                      a.service_name as service_name,
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
                  a.appointment_date as appointment_date,
                  a.appointment_time as appointment_time
           FROM queue q
           JOIN doctors d ON q.doctor_id = d.id
           LEFT JOIN appointments a ON q.appointment_id = a.id
           WHERE q.status NOT IN ('завершён', 'не_пришёл')
           ORDER BY q.called_at, q.id"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in queue]


@app.post("/api/queue")
def add_to_queue(data: dict):
    """Добавить в очередь. Клиент отправляет {"appointment_id": <id>}"""
    appointment_id = (data or {}).get("appointment_id")
    if not appointment_id:
        raise HTTPException(status_code=400, detail="appointment_id required")

    if USE_POSTGRES:
        # берём нужные поля из appointments (для совместимости со схемой queue в вашей БД)
        apt = pg_query_one(
            "SELECT id, doctor_id, patient_name, phone, appointment_date, appointment_time, service_name "
            "FROM public.appointments WHERE id = %s",
            (appointment_id,),
        )
        if not apt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        # не добавляем дубли (ожидание/вызван/в работе)
        existing = pg_query_one(
            """SELECT id FROM public.queue
               WHERE appointment_id = %s AND status NOT IN ('завершён','не_пришёл')
               LIMIT 1""",
            (appointment_id,),
        )
        if existing:
            return {"success": True, "id": int(existing["id"])}

        # Подстраиваемся под реальную структуру таблицы queue в Postgres (она могла быть создана ранее другим кодом)
        cols_meta = pg_table_columns("queue")
        cols = {c["column_name"] for c in cols_meta}

        insert_cols = []
        insert_vals = []
        insert_exprs = []

        def add_col(col, val, use_now=False):
            if col not in cols:
                return
            insert_cols.append(col)
            if use_now:
                insert_exprs.append("now()")
            else:
                insert_exprs.append("%s")
                insert_vals.append(val)

        # Базовые поля
        add_col("appointment_id", int(apt["id"]))
        add_col("doctor_id", int(apt["doctor_id"]))
        add_col("status", "ожидание")
        # В некоторых схемах called_at / created_at обязательны
        add_col("called_at", None, use_now=True)

        # Часто встречающиеся доп.поля (если они есть и/или NOT NULL)
        add_col("patient_name", apt.get("patient_name") or "")
        add_col("phone", apt.get("phone") or "")
        add_col("appointment_date", apt.get("appointment_date"))
        add_col("appointment_time", apt.get("appointment_time") or "")
        add_col("service_name", apt.get("service_name") or "")

        # Сформировать SQL
        if not insert_cols:
            # Фолбэк: минимальная вставка (на случай, если table columns не прочитались)
            new_id = pg_execute(
                """INSERT INTO public.queue (appointment_id, doctor_id, status, called_at)
                   VALUES (%s, %s, 'ожидание', now())
                   RETURNING id""",
                (appointment_id, apt["doctor_id"]),
                returning_id=True,
            )
            return {"success": True, "id": int(new_id)}

        sql = (
            "INSERT INTO public.queue (" + ", ".join(insert_cols) + ") "
            "VALUES (" + ", ".join(insert_exprs) + ") RETURNING id"
        )
        new_id = pg_execute(sql, tuple(insert_vals), returning_id=True)
        return {"success": True, "id": int(new_id)}
    conn = get_db_sqlite()
    cur = conn.cursor()
    apt = cur.execute("SELECT id, doctor_id FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
    if not apt:
        conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    existing = cur.execute(
        """SELECT id FROM queue
           WHERE appointment_id = ? AND status NOT IN ('завершён','не_пришёл')
           LIMIT 1""",
        (appointment_id,),
    ).fetchone()
    if existing:
        qid = existing["id"]
        conn.close()
        return {"success": True, "id": qid}

    cur.execute(
        "INSERT INTO queue (appointment_id, doctor_id, status, called_at) VALUES (?, ?, 'ожидание', ?)",
        (appointment_id, apt["doctor_id"], datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    qid = cur.lastrowid
    conn.close()
    return {"success": True, "id": qid}


@app.put("/api/queue/{queue_id}/status")
def update_queue_status(queue_id: int, data: dict):
    """Обновить статус элемента очереди. Клиент шлёт {"status": "..."}"""
    status = (data or {}).get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status required")

    # если статус меняется на "вызван/в_работе" и called_at пустой — ставим время
    now_iso = datetime.now().isoformat(timespec="seconds")

    if USE_POSTGRES:
        row = pg_query_one("SELECT id, called_at FROM public.queue WHERE id = %s", (queue_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Queue item not found")

        if row.get("called_at") is None:
            pg_execute("UPDATE public.queue SET status = %s, called_at = now() WHERE id = %s", (status, queue_id))
        else:
            pg_execute("UPDATE public.queue SET status = %s WHERE id = %s", (status, queue_id))
        return {"success": True}

    conn = get_db_sqlite()
    cur = conn.cursor()
    row = cur.execute("SELECT id, called_at FROM queue WHERE id = ?", (queue_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Queue item not found")

    if row["called_at"] is None:
        cur.execute("UPDATE queue SET status = ?, called_at = ? WHERE id = ?", (status, now_iso, queue_id))
    else:
        cur.execute("UPDATE queue SET status = ? WHERE id = ?", (status, queue_id))
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
        pg_execute("UPDATE public.appointments SET status = 'отменена' WHERE id = %s", (apt_id,))
        return {"success": True}

    conn = get_db_sqlite()
    conn.execute("UPDATE appointments SET status = 'отменена' WHERE id = ?", (apt_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/stats")
def get_stats():
    if USE_POSTGRES:
        total = pg_query_one("SELECT COUNT(*)::int as cnt FROM public.appointments")["cnt"]
        active = pg_query_one("SELECT COUNT(*)::int as cnt FROM public.appointments WHERE status = 'активна'")["cnt"]
        cancelled = pg_query_one("SELECT COUNT(*)::int as cnt FROM public.appointments WHERE status = 'отменена'")["cnt"]
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
