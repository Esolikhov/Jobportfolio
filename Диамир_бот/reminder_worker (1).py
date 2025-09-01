# reminder_worker.py
import time
import signal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sheets_api import get_all_meds_schedules
from whatsapp_api import send_whatsapp_message

# === НАСТРОЙКИ ===
TZ = ZoneInfo("Asia/Dushanbe")
LOOP_INTERVAL_SECONDS = 20          # тик каждые ~20 сек
WINDOW_SECONDS = 30                 # окно срабатывания ±30 сек

_running = True
def _sig_handler(signum, frame):
    global _running
    print("[REM] [SHUTDOWN] got signal", signum, "stopping loop...", flush=True)
    _running = False

signal.signal(signal.SIGINT, _sig_handler)
signal.signal(signal.SIGTERM, _sig_handler)

# Маппинги «человеческого» времени -> (час, минута) по Душанбе
TIME_MAPPINGS = {
    "до завтрака": (7, 0),
    "после завтрака": (8, 0),
    "утром после еды": (9, 0),
    "после еды утром": (9, 0),
    "утром после завтрака": (9, 0),
    "после обеда": (14, 0),
    "обед": (13, 0),
    "ужин": (19, 0),
    "после ужина": (20, 0),
    "утро": (8, 0),
    "день": (13, 0),
    "вечер": (19, 0),
}

def parse_time_str(time_str: str | None):
    """
    'до завтрака' -> (7,0)
    'Утром после еды' -> (9,0)
    '18:30' -> (18,30)
    '9' -> (9,0)
    """
    if not time_str:
        return None
    s = str(time_str).strip().lower()

    # точные маппинги
    if s in TIME_MAPPINGS:
        return TIME_MAPPINGS[s]

    # композиции вида "утром ...", "после еды ..."
    if "утр" in s and "после" in s and ("ед" in s or "завтрак" in s):
        return (9, 0)
    if "вечер" in s and "после" in s and ("ед" in s or "ужин" in s):
        return (20, 0)

    if ":" in s:
        try:
            h, m = s.split(":")
            return int(h), int(m)
        except Exception:
            return None
    try:
        h = int(s)
        if 0 <= h < 24:
            return (h, 0)
    except Exception:
        pass
    return None

def today_event_time(hour: int, minute: int, now: datetime) -> datetime:
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

def in_window(now: datetime, target: datetime, delta_sec: int, window: int = WINDOW_SECONDS) -> bool:
    edge = target - timedelta(seconds=delta_sec)
    return abs((now - edge).total_seconds()) <= window

def already_notified(notification_log: dict, when_key: str) -> bool:
    return notification_log.get(when_key) is True

def set_notified(notification_log: dict, when_key: str) -> None:
    notification_log[when_key] = True

def make_key(phone: str, event_dt: datetime, med_name: str, typ: str) -> str:
    hm = f"{event_dt:%H:%M}"
    date = f"{event_dt:%Y-%m-%d}"
    return f"{phone}|{date}|{hm}|med:{med_name}|typ:{typ}"

def main():
    print("== Диамир напоминалка стартовала ==", flush=True)
    print(f"[REM] TZ: {TZ}", flush=True)

    notification_log: dict[str, bool] = {}
    current_log_date = datetime.now(TZ).date()

    while _running:
        try:
            now = datetime.now(TZ)

            # Новые сутки — очищаем лог
            if now.date() != current_log_date:
                notification_log.clear()
                current_log_date = now.date()
                print(f"[REM] Новый день {current_log_date}, лог очищен", flush=True)

            # ЧИТАЕМ SAMPLE ОДИН РАЗ: получаем {phone->schedule}
            schedules = get_all_meds_schedules()  # одна операция чтения листа
            if not schedules:
                time.sleep(LOOP_INTERVAL_SECONDS)
                continue

            for phone, sched in schedules.items():
                for idx in ("1", "2"):
                    med_name = (sched.get(f"med{idx}_name") or "").strip()
                    med_time_str = (sched.get(f"med{idx}_time") or "").strip()
                    if not med_name or not med_time_str:
                        continue

                    parsed = parse_time_str(med_time_str)
                    if parsed is None:
                        print(f"[REM] {phone}: не распознал время '{med_time_str}'", flush=True)
                        continue

                    hour, minute = parsed
                    event_dt = today_event_time(hour, minute, now)

                    # 1 час до
                    key_1h = make_key(phone, event_dt, med_name, "1h")
                    if in_window(now, event_dt, 3600) and not already_notified(notification_log, key_1h):
                        send_whatsapp_message(phone, f"⏰ Через 1 час приём препарата {med_name} в {hour:02d}:{minute:02d}.")
                        set_notified(notification_log, key_1h)
                        print(f"[REM] 1h -> {phone} {med_name} {hour:02d}:{minute:02d}", flush=True)

                    # 5 минут до
                    key_5m = make_key(phone, event_dt, med_name, "5m")
                    if in_window(now, event_dt, 300) and not already_notified(notification_log, key_5m):
                        send_whatsapp_message(phone, f"⏰ Через 5 минут приём препарата {med_name} в {hour:02d}:{minute:02d}.")
                        set_notified(notification_log, key_5m)
                        print(f"[REM] 5m -> {phone} {med_name} {hour:02d}:{minute:02d}", flush=True)

                    # Ровно в момент
                    key_0m = make_key(phone, event_dt, med_name, "0m")
                    if in_window(now, event_dt, 0) and not already_notified(notification_log, key_0m):
                        send_whatsapp_message(phone, f"💊 Время приёма препарата {med_name}: {hour:02d}:{minute:02d}.")
                        set_notified(notification_log, key_0m)
                        print(f"[REM] 0m -> {phone} {med_name} {hour:02d}:{minute:02d}", flush=True)

        except Exception as e:
            # не роняем процесс, просто логируем
            print(f"[REM][ERR] {e}", flush=True)

        time.sleep(LOOP_INTERVAL_SECONDS)

    print("=== reminder_worker: остановлен ===", flush=True)

if __name__ == "__main__":
    main()
