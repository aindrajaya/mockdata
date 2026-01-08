from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class WorkOrder(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: str
    assignee: str
    department: str
    workType: str
    createdDate: str
    dueDate: str
    estimatedHours: int
    completionPercentage: int


app = FastAPI(title="Work Orders API", version="1.0.0")
DATA_PATH = Path(__file__).with_name("workOrders-50k.json")


@lru_cache(maxsize=1)
def load_workorders() -> List[dict]:
    try:
        with DATA_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing data file: {DATA_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {DATA_PATH}: {exc}") from exc

    if not isinstance(data, list):
        raise RuntimeError("Work orders data is not a JSON array.")

    return data


@app.get("/workorders", response_model=List[WorkOrder])
def list_workorders():
    try:
        return load_workorders()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
