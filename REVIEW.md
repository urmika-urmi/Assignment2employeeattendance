# REVIEW.md
# Employee Attendance & Analytics API

Run: pip install -r requirements.txt, set MONGO_URI and MONGO_DB, then uvicorn app.main:app --port 8000

## Done
- Employee create and list, punch-in, punch-out, attendance list
- Fixed helper functions for late minutes, work hours and overtime

## Not done (ran out of time)
- PATCH correction endpoint
- All analytics endpoints
- Admin explain endpoint
- Unique indexes at startup
- REVIEW.md and DECISIONS.md are not filled in
List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | | | | |

Also note anything you looked at and decided was **not** a defect, and why.
