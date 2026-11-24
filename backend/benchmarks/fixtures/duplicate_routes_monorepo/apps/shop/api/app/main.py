from fastapi import FastAPI

app = FastAPI()


@app.get("/orders")
def list_orders():
    return {"service": "shop"}