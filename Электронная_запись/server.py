#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3
from datetime import datetime
import uvicorn
import os

DATABASE = 'dental_clinic.db'
app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class AppointmentCreate(BaseModel):
    patient_name: str
    phone: str
    doctor_id: int
    appointment_date: str
    appointment_time: str
    service_name: str | None = None


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Мягкая миграция БД без потери данных."""
    cur = conn.cursor()
    # appointments.service_name
    cols = [r[1] for r in cur.execute("PRAGMA table_info(appointments)").fetchall()]
    if "service_name" not in cols:
        cur.execute("ALTER TABLE appointments ADD COLUMN service_name TEXT")
    conn.commit()

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn

@app.get("/")
def read_root():
    # API может разворачиваться отдельно от фронтенда.
    # Если папка website существует — покажем сайт, иначе вернём статус.
    if os.path.exists('website/index.html'):
        return FileResponse('website/index.html')
    return {"status": "ok", "service": "dental-backend"}

@app.get("/api/doctors")
def get_doctors():
    conn = get_db()
    doctors = conn.execute('SELECT * FROM doctors WHERE is_active = 1').fetchall()
    conn.close()
    return [dict(row) for row in doctors]

@app.get("/api/available-slots")
def get_available_slots(doctor_id: int, date: str):
    conn = get_db()
    slots = []
    for hour in range(8, 17):
        for minute in [0, 30]:
            time_str = f"{hour:02d}:{minute:02d}"
            existing = conn.execute("SELECT id FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ? AND status = 'активна'", (doctor_id, date, time_str)).fetchone()
            slots.append({'time': time_str, 'available': existing is None})
    conn.close()
    return slots

@app.post("/api/appointments")
def create_appointment(appointment: AppointmentCreate):
    conn = get_db()
    cursor = conn.cursor()
    existing = cursor.execute("SELECT id FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ? AND status = 'активна'", (appointment.doctor_id, appointment.appointment_date, appointment.appointment_time)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Время занято")
    cursor.execute(
        """INSERT INTO appointments (patient_name, phone, doctor_id, appointment_date, appointment_time, service_name, status)
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
    return {'success': True, 'id': apt_id}

@app.get("/api/appointments/today")
def get_today_appointments(date: str = None):
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
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


@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/queue")
def get_queue():
    conn = get_db()
    queue = conn.execute("SELECT q.*, d.name as doctor_name FROM queue q JOIN doctors d ON q.doctor_id = d.id WHERE q.status NOT IN ('завершён', 'не_пришёл') ORDER BY q.called_at").fetchall()
    conn.close()
    return [dict(row) for row in queue]

@app.put("/api/doctors/{doctor_id}/status")
def update_doctor_status(doctor_id: int, data: dict):
    conn = get_db()
    conn.execute("UPDATE doctors SET status = ? WHERE id = ?", (data['status'], doctor_id))
    conn.commit()
    conn.close()
    return {'success': True}

@app.put("/api/appointments/{apt_id}/cancel")
def cancel_appointment(apt_id: int):
    conn = get_db()
    conn.execute("UPDATE appointments SET status = 'отменена' WHERE id = ?", (apt_id,))
    conn.commit()
    conn.close()
    return {'success': True}

@app.get("/api/stats")
def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as cnt FROM appointments").fetchone()['cnt']
    active = conn.execute("SELECT COUNT(*) as cnt FROM appointments WHERE status = 'активна'").fetchone()['cnt']
    cancelled = conn.execute("SELECT COUNT(*) as cnt FROM appointments WHERE status = 'отменена'").fetchone()['cnt']
    completed = conn.execute("SELECT COUNT(*) as cnt FROM queue WHERE status = 'завершён'").fetchone()['cnt']
    doctors_stats = conn.execute("SELECT d.name, COUNT(q.id) as completed_count FROM doctors d LEFT JOIN queue q ON d.id = q.doctor_id AND q.status = 'завершён' GROUP BY d.id, d.name").fetchall()
    conn.close()
    return {'total': total, 'active': active, 'cancelled': cancelled, 'completed': completed, 'doctors': [dict(row) for row in doctors_stats]}

if os.path.isdir("website"):
    app.mount("/website", StaticFiles(directory="website"), name="website")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("СЕРВЕР: http://localhost:8000")
    print("САЙТ: http://localhost:8000/website/index.html")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
