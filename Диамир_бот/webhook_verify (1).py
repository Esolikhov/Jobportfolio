from fastapi import FastAPI, Request

VERIFY_TOKEN = "verify_token_123"

app = FastAPI()

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == VERIFY_TOKEN
    ):
        return int(params.get("hub.challenge"))
    return "Verification failed"

@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    print("Получено событие:", data)
    # Здесь можно добавить обработку сообщений
    return {"status": "ok"}
