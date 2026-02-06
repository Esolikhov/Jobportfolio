#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime
import uvicorn
import os

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
    """Мягкая миграция SQLite БД без потери данных."""
    cur = conn.cursor()
    # appointments.service_name
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(appointments)").fetchall()]
        if "service_name" not in cols:
            cur.execute("ALTER TABLE appointments ADD COLUMN service_name TEXT")
            conn.commit()
    except Exception:
        # если таблицы ещё нет — ничего
        pass

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

def ensure_schema_pg():
    """Добавляет отсутствующие колонки (без потери данных)."""
    _init_pg_pool()
    conn = _pg_pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # appointments.service_name (если нет в create_db.py)
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
    finally:
        _pg_pool.putconn(conn)

def pg_query_all(sql: str, params=None):
    from psycopg2.extras import RealDictCursor
    _init_pg_pool()
    ensure_schema_pg()
    conn = _pg_pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        _pg_pool.putconn(conn)

def pg_query_one(sql: str, params=None):
    from psycopg2.extras import RealDictCursor
    _init_pg_pool()
    ensure_schema_pg()
    conn = _pg_pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    finally:
        _pg_pool.putconn(conn)

def pg_execute(sql: str, params=None, returning_id: bool = False):
    _init_pg_pool()
    ensure_schema_pg()
    conn = _pg_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            new_id = None
            if returning_id:
                new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    finally:
        _pg_pool.putconn(conn)


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
    slots = []
    if USE_POSTGRES:
        for hour in range(8, 17):
            for minute in (0, 30):
                time_str = f"{hour:02d}:{minute:02d}"
                existing = pg_query_one(
                    "SELECT id FROM public.appointments WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s AND status = 'активна' LIMIT 1",
                    (doctor_id, date, time_str),
                )
                slots.append({"time": time_str, "available": existing is None})
        return slots

    conn = get_db_sqlite()
    for hour in range(8, 17):
        for minute in (0, 30):
            time_str = f"{hour:02d}:{minute:02d}"
            existing = conn.execute(
                "SELECT id FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ? AND status = 'активна'",
                (doctor_id, date, time_str),
            ).fetchone()
            slots.append({"time": time_str, "available": existing is None})
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
    if USE_POSTGRES:
        return pg_query_all(
            """SELECT q.*, d.name as doctor_name
               FROM public.queue q
               JOIN public.doctors d ON q.doctor_id = d.id
               WHERE q.status NOT IN ('завершён', 'не_пришёл')
               ORDER BY q.called_at"""
        )

    conn = get_db_sqlite()
    queue = conn.execute(
        """SELECT q.*, d.name as doctor_name
           FROM queue q
           JOIN doctors d ON q.doctor_id = d.id
           WHERE q.status NOT IN ('завершён', 'не_пришёл')
           ORDER BY q.called_at"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in queue]


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
