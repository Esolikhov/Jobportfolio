# daily_tasks_worker.py
import time
import signal
import pytz
from datetime import datetime

from sheets_api import get_all_user_phones_from_sample, get_daily_task_by_day
from whatsapp_api import send_whatsapp_message

# Таймзона Душанбе
DUSHANBE_TZ = pytz.timezone("Asia/Dushanbe")

# Во сколько отправлять задание по Душанбе
DAILY_HOUR = 8     # 08:00
DAILY_MINUTE = 0   # 08:00

_running = True
def _sig_handler(signum, frame):
    global _running
    print("[WORKER] [SHUTDOWN] got signal", signum, "stopping loop...", flush=True)
    _running = False

signal.signal(signal.SIGINT, _sig_handler)
signal.signal(signal.SIGTERM, _sig_handler)

def send_daily_tasks():
    users = get_all_user_phones_from_sample()  # БЕЗ привязки к заголовкам
    now_dushanbe = datetime.now(DUSHANBE_TZ)
    day_num = now_dushanbe.timetuple().tm_yday
    task = get_daily_task_by_day(day_num)

    print(f"[WORKER] {now_dushanbe.strftime('%Y-%m-%d %H:%M:%S %Z')} — "
          f"Шлём задание дня пользователям: {len(users)}", flush=True)

    title = (task.get("Task", "") or "").strip()
    desc  = (task.get("Description", "") or "").strip()
    msg = f"📝 *Задание дня*\n{title}\n{desc}".strip()

    for phone in users:
        try:
            resp = send_whatsapp_message(phone, msg)
            code = getattr(resp, "status_code", "?")
            body = getattr(resp, "text", "?")
            print(f"[WA][{phone}] status={code} body={body}", flush=True)
        except Exception as e:
            print(f"[WA][{phone}] error: {e}", flush=True)

def main():
    """
    Бесконечный цикл: каждую минуту смотрим локальное время Душанбе и,
    если наступили 08:00, отсылаем «Задание дня» один раз в сутки.
    """
    print("=== daily_tasks_worker: старт ===", flush=True)
    last_sent_date = None  # YYYY-MM-DD строки, чтобы не дублировать за день

    while _running:
        try:
            now_dushanbe = datetime.now(DUSHANBE_TZ)
            cur_date = now_dushanbe.strftime("%Y-%m-%d")
            hour = now_dushanbe.hour
            minute = now_dushanbe.minute

            # Ровно в 08:00 по Душанбе — если ещё не отправляли сегодня
            if hour == DAILY_HOUR and minute == DAILY_MINUTE:
                if last_sent_date != cur_date:
                    send_daily_tasks()
                    last_sent_date = cur_date
                    print(f"[WORKER] Отправлено за {cur_date}", flush=True)
        except Exception as e:
            print(f"[WORKER] Ошибка при отправке: {e}", flush=True)

        time.sleep(60)

    print("=== daily_tasks_worker: остановлен ===", flush=True)

if __name__ == "__main__":
    main()
