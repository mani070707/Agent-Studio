from fastapi import FastAPI

app = FastAPI(title="Agent Studio API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
