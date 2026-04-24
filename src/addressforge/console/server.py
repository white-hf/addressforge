from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI(title="AddressForge Console")


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.getenv("ADDRESSFORGE_CONSOLE_PORT", "8011"))
    uvicorn.run("addressforge.console.server:app", host="127.0.0.1", port=port, reload=False)
