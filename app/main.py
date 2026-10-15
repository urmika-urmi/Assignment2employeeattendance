"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient


load_dotenv()

client = MongoClient(
    os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    tz_aware=True
)
db = client[os.getenv("MONGO_DB", "attendance_db")]
db.attendance_logs.create_index(
    [("emp_code", 1), ("date", 1)],
    unique=True
)

IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


UTC = timezone.utc


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms // 1000, tz=UTC)


def dt_to_ms(dt: datetime) -> int:
    return int(dt.timestamp()) * 1000


def shift_window(punch_in: datetime, shift_start: str, shift_end: str):
    local = punch_in.astimezone(IST)
    sh, sm = map(int, shift_start.split(":"))
    eh, em = map(int, shift_end.split(":"))
    overnight = (eh, em) <= (sh, sm)

    day = local.date()
    if overnight and (local.hour, local.minute) < (eh, em):
        day -= timedelta(days=1)

    start_dt = datetime(day.year, day.month, day.day, sh, sm, tzinfo=IST)
    end_dt = datetime(day.year, day.month, day.day, eh, em, tzinfo=IST)

    if overnight:
        end_dt += timedelta(days=1)

    return day.isoformat(), start_dt, end_dt


def compute_late_minutes(punch_in: datetime, shift_start_dt: datetime) -> int:
    seconds = (punch_in - shift_start_dt).total_seconds()
    return int(seconds // 60) if seconds > 600 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    seconds = Decimal(int((punch_out - punch_in).total_seconds()))
    hours = (seconds / Decimal(3600)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return float(hours)


def compute_overtime(punch_out: datetime, shift_end_dt: datetime) -> int:
    minutes = int((punch_out - shift_end_dt).total_seconds() // 60)
    return minutes if minutes >= 30 else 0

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str
    name: str
    email: str
    department: str
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(409, "emp_code already exists")
    doc = body.model_dump()
    doc["created_at"] = datetime.now()
    db.employees.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.get("/employees")
def list_employees(department: Optional[str] = None, page: int = 1, page_size: int = 20):
    q = {}
    if department:
        q["department"] = department
    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)
    items = list(db.employees.find(q, {"_id": 0}).skip(skip).limit(page_size))
    return {"items": items, "total": total, "page": page, "page_size": page_size}



@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    # 1. Find the employee
    emp = db.employees.find_one({"emp_code": body.emp_code})

    # 2. Return 404 if employee does not exist
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    # 3. Convert timestamp to UTC
    ts = (
        ms_to_dt(body.punched_at)
        if body.punched_at is not None
        else datetime.now(UTC)
    )

    # 4. Calculate the attendance date and shift times
    attendance_date, shift_start_dt, shift_end_dt = shift_window(
        ts, emp["shift_start"], emp["shift_end"]
    )

    # 5. Prevent duplicate attendance for the same date
    existing = db.attendance_logs.find_one({
        "emp_code": body.emp_code,
        "date": attendance_date
    })

    if existing:
        raise HTTPException(
            status_code=409,
            detail="already punched in for this date"
        )

    # 6. Create the attendance record
    doc = {
        "emp_code": body.emp_code,
        "date": attendance_date,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, shift_start_dt),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    # 7. Save the record in MongoDB
    res = db.attendance_logs.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc



@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    # Keep your existing list_attendance function here.
    # Do not delete your existing function body.
    pass


# ADD THE NEW CODE BELOW list_attendance()

class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    ts = (
        ms_to_dt(body.punched_at)
        if body.punched_at is not None
        else datetime.now(UTC)
    )

    attendance_date, shift_start_dt, shift_end_dt = shift_window(
        ts, emp["shift_start"], emp["shift_end"]
    )

    record = db.attendance_logs.find_one({
        "emp_code": body.emp_code,
        "date": attendance_date
    })

    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    if record.get("punch_out") is not None:
        raise HTTPException(status_code=409, detail="Already punched out")

    if ts < record["punch_in"]:
        raise HTTPException(status_code=400, detail="Punch-out cannot be before punch-in")

    work_hours = compute_work_hours(record["punch_in"], ts)
    overtime_minutes = compute_overtime(ts, shift_end_dt)

    db.attendance_logs.update_one(
        {"_id": record["_id"]},
        {"$set": {
            "punch_out": ts,
            "work_hours": work_hours,
            "overtime_minutes": overtime_minutes,
            "half_day": work_hours < 4
        }}
    )

    updated = db.attendance_logs.find_one({"_id": record["_id"]})
    updated["id"] = str(updated.pop("_id"))
    return updated


# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
