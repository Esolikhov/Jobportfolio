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
            try:
                # tables (idempotent)
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS public.doctors (
                        id serial PRIMARY KEY,
                        name text NOT NULL,
                        room text DEFAULT '',
                        status text DEFAULT 'доступен',
                        is_active integer DEFAULT 1
                    )"""
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS public.appointments (
                        id serial PRIMARY KEY,
                        patient_name text NOT NULL,
                        phone text DEFAULT '',
                        doctor_id integer NOT NULL,
                        appointment_date text NOT NULL,
                        appointment_time text NOT NULL,
                        service_name text,
                        status text DEFAULT 'активна',
                        created_at timestamp DEFAULT now()
                    )"""
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS public.queue (
                        id serial PRIMARY KEY,
                        appointment_id integer NOT NULL,
                        doctor_id integer NOT NULL,
                        status text DEFAULT 'ожидание',
                        called_at timestamp,
                        created_at timestamp DEFAULT now()
                    )"""
                )
            except Exception:
                pass

            # columns (add if missing)
            try:
                cur.execute(
                    "ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS room text DEFAULT ''"
                )
                cur.execute(
                    "ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS status text DEFAULT 'доступен'"
                )
                cur.execute(
                    "ALTER TABLE public.doctors ADD COLUMN IF NOT EXISTS is_active integer DEFAULT 1"
                )
            except Exception:
                pass
            try:
                cur.execute(
                    "ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS service_name text"
                )
                cur.execute(
                    "ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS status text DEFAULT 'активна'"
                )
            except Exception:
                pass
            try:
                cur.execute(
                    "ALTER TABLE public.queue ADD COLUMN IF NOT EXISTS called_at timestamp"
                )
                cur.execute(
                    "ALTER TABLE public.queue ADD COLUMN IF NOT EXISTS status text DEFAULT 'ожидание'"
                )
            except Exception:
                pass
    finally:
        _pg_putconn(conn, _key)


ensure_schema_pg()


def pg_has_column(table_name: str, col_name: str) -> bool:
    """Проверяем, есть ли колонка."""
    conn, key = _pg_getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT column_name
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = %s
                     AND column_name = %s""",
                (table_name, col_name),
            )
            return cur.fetchone() is not None
    finally:
        _pg_putconn(conn, key)


def pg_execute(sql: str, params: tuple = (), returning_id: bool = False):
    """Выполняет UPDATE/INSERT/DELETE с автокоммитом"""
    conn, key = _pg_getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if returning_id:
                row = cur.fetchone()
                return row[0] if row else None
    finally:
        _pg_putconn(conn, key)


def pg_query_all(sql: str, params: tuple = ()):
    """Возвращает список словарей"""
    conn, key = _pg_getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
            return [dict(zip(cols, r)) for r in rows]
    finally:
        _pg_putconn(conn, key)


def pg_query_one(sql: str, params: tuple = ()):
    """Возвращает один словарь или None"""
    conn, key = _pg_getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))
    finally:
        _pg_putconn(conn, key)


# ==============================
# API endpoints
# ==============================
@app.get("/api/doctors")
def get_doctors():
    if USE_POSTGRES:
        docs = pg_query_all("SELECT id, name, room, status FROM public.doctors WHERE is_active = 1 ORDER BY id")
        return docs

    conn = get_db_sqlite()
    rows = conn.execute("SELECT id, name, room, status FROM doctors WHERE is_active = 1 ORDER BY id").fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/doctors")
def create_doctor(data: dict):
    name = data.get("name", "").strip()
    room = data.get("room", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    if USE_POSTGRES:
        new_id = pg_execute(
            "INSERT INTO public.doctors (name, room, status) VALUES (%s, %s, 'доступен') RETURNING id",
            (name, room),
            returning_id=True,
        )
        return {"success": True, "id": int(new_id)}

    conn = get_db_sqlite()
    cur = conn.cursor()
    cur.execute("INSERT INTO doctors (name, room, status) VALUES (?, ?, 'доступен')", (name, room))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"success": True, "id": int(new_id)}


@app.get("/api/appointments")
def get_appointments(date: str = None):
    if date:
        date = normalize_date_str(date)

    if USE_POSTGRES:
        if date:
            rows = pg_query_all(
                """SELECT a.id, a.patient_name, a.phone, a.doctor_id, a.appointment_date, a.appointment_time,
                          a.service_name, a.status, d.name as doctor_name
                   FROM public.appointments a
                   JOIN public.doctors d ON a.doctor_id = d.id
                   WHERE a.appointment_date = %s AND a.status = 'активна'
                   ORDER BY a.appointment_time""",
                (date,),
            )
        else:
            rows = pg_query_all(
                """SELECT a.id, a.patient_name, a.phone, a.doctor_id, a.appointment_date, a.appointment_time,
                          a.service_name, a.status, d.name as doctor_name
                   FROM public.appointments a
                   JOIN public.doctors d ON a.doctor_id = d.id
                   WHERE a.status = 'активна'
                   ORDER BY a.appointment_date, a.appointment_time"""
            )
        return rows

    conn = get_db_sqlite()
    if date:
        rows = conn.execute(
            """SELECT a.id, a.patient_name, a.phone, a.doctor_id, a.appointment_date, a.appointment_time,
                      a.service_name, a.status, d.name as doctor_name
               FROM appointments a
               JOIN doctors d ON a.doctor_id = d.id
               WHERE a.appointment_date = ? AND a.status = 'активна'
               ORDER BY a.appointment_time""",
            (date,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT a.id, a.patient_name, a.phone, a.doctor_id, a.appointment_date, a.appointment_time,
                      a.service_name, a.status, d.name as doctor_name
               FROM appointments a
               JOIN doctors d ON a.doctor_id = d.id
               WHERE a.status = 'активна'
               ORDER BY a.appointment_date, a.appointment_time"""
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/appointments")
def create_appointment(apt: AppointmentCreate):
    apt_date = normalize_date_str(apt.appointment_date)

    if USE_POSTGRES:
        new_id = pg_execute(
            """INSERT INTO public.appointments (patient_name, phone, doctor_id, appointment_date, appointment_time, service_name, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'активна')
               RETURNING id""",
            (apt.patient_name, apt.phone, apt.doctor_id, apt_date, apt.appointment_time, apt.service_name),
            returning_id=True,
        )
        return {"success": True, "id": int(new_id)}

    conn = get_db_sqlite()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO appointments (patient_name, phone, doctor_id, appointment_date, appointment_time, service_name, status)
           VALUES (?, ?, ?, ?, ?, ?, 'активна')""",
        (apt.patient_name, apt.phone, apt.doctor_id, apt_date, apt.appointment_time, apt.service_name),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"success": True, "id": int(new_id)}


@app.get("/api/queue")
def get_queue():
    if USE_POSTGRES:
        rows = pg_query_all(
            """SELECT q.id, q.appointment_id, q.doctor_id, q.status, q.called_at,
                      a.patient_name, a.phone, a.service_name,
                      d.name as doctor_name, d.room
               FROM public.queue q
               JOIN public.appointments a ON q.appointment_id = a.id
               JOIN public.doctors d ON q.doctor_id = d.id
               WHERE q.status NOT IN ('завершён', 'не_пришёл')
               ORDER BY q.id"""
        )
        return rows

    conn = get_db_sqlite()
    rows = conn.execute(
        """SELECT q.id, q.appointment_id, q.doctor_id, q.status, q.called_at,
                  a.patient_name, a.phone, a.service_name,
                  d.name as doctor_name, d.room
           FROM queue q
           JOIN appointments a ON q.appointment_id = a.id
           JOIN doctors d ON q.doctor_id = d.id
           WHERE q.status NOT IN ('завершён', 'не_пришёл')
           ORDER BY q.id"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/queue")
def add_to_queue(data: dict):
    appointment_id = data.get("appointment_id")
    if not appointment_id:
        raise HTTPException(status_code=400, detail="appointment_id required")

    if USE_POSTGRES:
        # Проверяем существование записи
        apt = pg_query_one("SELECT id, doctor_id, patient_name, phone FROM public.appointments WHERE id = %s", (appointment_id,))
        if not apt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        # Проверяем, не в очереди ли уже
        existing = pg_query_one(
            "SELECT id FROM public.queue WHERE appointment_id = %s AND status NOT IN ('завершён','не_пришёл') LIMIT 1",
            (appointment_id,),
        )
        if existing:
            return {"success": True, "id": int(existing["id"])}

        patient_name = (data or {}).get("patient_name") or apt["patient_name"] or "Без имени"
        phone = (data or {}).get("phone") or apt["phone"]

        # room
        room = (data or {}).get("room")
        if not room:
            try:
                if pg_has_column("doctors", "room"):
                    d = pg_query_one("SELECT room FROM public.doctors WHERE id = %s", (apt["doctor_id"],))
                    room = (d or {}).get("room")
            except Exception:
                room = None
        if room is None:
            room = "1"

        # Вставляем в очередь
        new_id = pg_execute(
            """INSERT INTO public.queue (appointment_id, doctor_id, status)
               VALUES (%s, %s, 'ожидание')
               RETURNING id""",
            (int(appointment_id), int(apt["doctor_id"])),
            returning_id=True,
        )
        return {"success": True, "id": int(new_id)}

    # SQLite режим
    conn = get_db_sqlite()
    try:
        cur = conn.cursor()
        apt = cur.execute("SELECT id, doctor_id, patient_name, phone FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        if not apt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        existing = cur.execute(
            "SELECT id FROM queue WHERE appointment_id = ? AND status NOT IN ('завершён','не_пришёл') LIMIT 1",
            (appointment_id,),
        ).fetchone()
        if existing:
            return {"success": True, "id": int(existing["id"])}

        patient_name = (data or {}).get("patient_name") or apt["patient_name"] or "Без имени"
        phone = (data or {}).get("phone") or apt["phone"]

        # room
        room = (data or {}).get("room")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(queue)").fetchall()]
        if "room" in cols and not room:
            try:
                d = cur.execute("SELECT room FROM doctors WHERE id = ?", (apt["doctor_id"],)).fetchone()
                room = d["room"] if d else ""
            except Exception:
                room = ""
        if room is None:
            room = ""

        insert_cols = ["appointment_id", "doctor_id", "patient_name", "status"]
        insert_vals = [appointment_id, apt["doctor_id"], patient_name, "ожидание"]
        if "phone" in cols:
            insert_cols.append("phone"); insert_vals.append(phone)
        if "room" in cols:
            insert_cols.append("room"); insert_vals.append(room)

        qmarks = ", ".join(["?"] * len(insert_cols))
        cur.execute(f"INSERT INTO queue ({', '.join(insert_cols)}) VALUES ({qmarks})", tuple(insert_vals))
        conn.commit()
        new_id = cur.lastrowid
        return {"success": True, "id": int(new_id)}
    finally:
        conn.close()

@app.put("/api/queue/{queue_id}/status")
def update_queue_status(queue_id: int, data: dict):
    """Обновить статус элемента очереди и статус врача"""
    status = (data or {}).get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status required")

    # если статус меняется на "вызван/в_работе" и called_at пустой — ставим время
    now_iso = datetime.now().isoformat(timespec="seconds")

    if USE_POSTGRES:
        row = pg_query_one("SELECT id, called_at, doctor_id FROM public.queue WHERE id = %s", (queue_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Queue item not found")

        doctor_id = row.get("doctor_id")

        # Обновляем статус очереди
        if row.get("called_at") is None:
            pg_execute("UPDATE public.queue SET status = %s, called_at = now() WHERE id = %s", (status, queue_id))
        else:
            pg_execute("UPDATE public.queue SET status = %s WHERE id = %s", (status, queue_id))

        # Обновляем статус врача
        if status in ("готов", "в_работе"):
            pg_execute("UPDATE public.doctors SET status = 'занят' WHERE id = %s", (doctor_id,))
        elif status in ("завершён", "не_пришёл"):
            # Проверяем, есть ли еще активные пациенты у этого врача
            active = pg_query_one(
                "SELECT COUNT(*)::int as cnt FROM public.queue WHERE doctor_id = %s AND status IN ('ожидание', 'готов', 'в_работе')",
                (doctor_id,)
            )
            if active and active.get("cnt", 0) == 0:
                pg_execute("UPDATE public.doctors SET status = 'доступен' WHERE id = %s", (doctor_id,))

        return {"success": True}

    conn = get_db_sqlite()
    cur = conn.cursor()
    row = cur.execute("SELECT id, called_at, doctor_id FROM queue WHERE id = ?", (queue_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Queue item not found")

    doctor_id = row["doctor_id"]

    # Обновляем статус очереди
    if row["called_at"] is None:
        cur.execute("UPDATE queue SET status = ?, called_at = ? WHERE id = ?", (status, now_iso, queue_id))
    else:
        cur.execute("UPDATE queue SET status = ? WHERE id = ?", (status, queue_id))

    # Обновляем статус врача
    if status in ("готов", "в_работе"):
        cur.execute("UPDATE doctors SET status = 'занят' WHERE id = ?", (doctor_id,))
    elif status in ("завершён", "не_пришёл"):
        # Проверяем, есть ли еще активные пациенты у этого врача
        active = cur.execute(
            "SELECT COUNT(*) as cnt FROM queue WHERE doctor_id = ? AND status IN ('ожидание', 'готов', 'в_работе')",
            (doctor_id,)
        ).fetchone()
        if active and active["cnt"] == 0:
            cur.execute("UPDATE doctors SET status = 'доступен' WHERE id = ?", (doctor_id,))

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
    """Отмена записи и удаление из очереди"""
    if USE_POSTGRES:
        # Отменяем запись
        pg_execute("UPDATE public.appointments SET status = 'отменена' WHERE id = %s", (apt_id,))
        # Удаляем из очереди
        pg_execute("DELETE FROM public.queue WHERE appointment_id = %s", (apt_id,))
        return {"success": True}

    conn = get_db_sqlite()
    conn.execute("UPDATE appointments SET status = 'отменена' WHERE id = ?", (apt_id,))
    conn.execute("DELETE FROM queue WHERE appointment_id = ?", (apt_id,))
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
