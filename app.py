from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


app = FastAPI(title="Work Orders API", version="1.0.0")
DATA_PATH = Path(__file__).with_name("workOrders-50k.json")


@app.get("/workorders")
def list_workorders():
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Missing data file: {DATA_PATH}")
    return FileResponse(DATA_PATH, media_type="application/json")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
