from __future__ import annotations

import csv
import io
import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data.db"


class Zone(BaseModel):
    id: int
    name: str
    price_hour: int
    capacity: int


class BookingIn(BaseModel):
    date: str
    zone_id: int
    customer_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=10, max_length=16)
    start_hour: int = Field(ge=6, le=23)
    duration: int = Field(ge=1, le=12)
    status: Literal["pending", "confirmed", "paid"] = "pending"
    comment: str = Field(default="", max_length=300)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("+"):
            raise ValueError("Телефон должен начинаться с +")
        if not value[1:].isdigit():
            raise ValueError("Телефон должен содержать только цифры после +")
        return value

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Дата должна быть в формате YYYY-MM-DD") from exc
        return value


class Booking(BookingIn):
    id: int
    end_hour: int


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with closing(conn()) as c, c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS zones (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              price_hour INTEGER NOT NULL,
              capacity INTEGER NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date TEXT NOT NULL,
              zone_id INTEGER NOT NULL,
              customer_name TEXT NOT NULL,
              phone TEXT NOT NULL,
              start_hour INTEGER NOT NULL,
              end_hour INTEGER NOT NULL,
              status TEXT NOT NULL,
              comment TEXT NOT NULL,
              FOREIGN KEY(zone_id) REFERENCES zones(id)
            )
            """
        )

        has_zones = c.execute("SELECT COUNT(*) AS count FROM zones").fetchone()["count"]
        if not has_zones:
            seed = [
                (1, "Зона 1 · Беседка у воды", 600, 4),
                (2, "Зона 2 · Тихий берег", 550, 4),
                (3, "Зона 3 · Семейная", 700, 6),
                (4, "Зона 4 · Большая беседка", 850, 8),
                (5, "Зона 5 · VIP", 1200, 10),
                (6, "Зона 6 · Левый пирс", 650, 4),
                (7, "Зона 7 · Правый пирс", 650, 4),
                (8, "Зона 8 · Тень", 500, 3),
                (9, "Зона 9 · Сектор A", 580, 4),
                (10, "Зона 10 · Сектор B", 580, 4),
            ]
            c.executemany("INSERT INTO zones(id, name, price_hour, capacity) VALUES (?, ?, ?, ?)", seed)


app = FastAPI(title="Fishing Booking API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/zones", response_model=list[Zone])
def get_zones() -> list[Zone]:
    with closing(conn()) as c:
        rows = c.execute("SELECT * FROM zones ORDER BY id").fetchall()
        return [Zone(**dict(r)) for r in rows]


@app.get("/api/bookings", response_model=list[Booking])
def get_bookings(day: str = Query(..., alias="date")) -> list[Booking]:
    with closing(conn()) as c:
        rows = c.execute(
            "SELECT id, date, zone_id, customer_name, phone, start_hour, end_hour, status, comment FROM bookings WHERE date = ? ORDER BY start_hour, zone_id",
            (day,),
        ).fetchall()
        return [Booking(**dict(r), duration=dict(r)["end_hour"] - dict(r)["start_hour"]) for r in rows]


def check_conflict(c: sqlite3.Connection, payload: BookingIn, booking_id: Optional[int] = None) -> None:
    end_hour = payload.start_hour + payload.duration
    if end_hour > 24:
        raise HTTPException(400, "Бронь не может заканчиваться позже 24:00")
    sql = (
        "SELECT id FROM bookings WHERE date = ? AND zone_id = ? AND NOT (? <= start_hour OR ? >= end_hour)"
    )
    params = [payload.date, payload.zone_id, end_hour, payload.start_hour]
    if booking_id is not None:
        sql += " AND id != ?"
        params.append(booking_id)
    row = c.execute(sql, params).fetchone()
    if row:
        raise HTTPException(409, f"Конфликт с бронью #{row['id']}")


@app.post("/api/bookings", response_model=Booking)
def create_booking(payload: BookingIn) -> Booking:
    with closing(conn()) as c, c:
        check_conflict(c, payload)
        end_hour = payload.start_hour + payload.duration
        cur = c.execute(
            """
            INSERT INTO bookings(date, zone_id, customer_name, phone, start_hour, end_hour, status, comment)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.date,
                payload.zone_id,
                payload.customer_name,
                payload.phone,
                payload.start_hour,
                end_hour,
                payload.status,
                payload.comment,
            ),
        )
        booking_id = cur.lastrowid
        row = c.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return Booking(**dict(row), duration=end_hour - payload.start_hour)


@app.put("/api/bookings/{booking_id}", response_model=Booking)
def update_booking(booking_id: int, payload: BookingIn) -> Booking:
    with closing(conn()) as c, c:
        exists = c.execute("SELECT id FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if not exists:
            raise HTTPException(404, "Бронь не найдена")
        check_conflict(c, payload, booking_id=booking_id)
        end_hour = payload.start_hour + payload.duration
        c.execute(
            """
            UPDATE bookings
               SET date = ?, zone_id = ?, customer_name = ?, phone = ?, start_hour = ?, end_hour = ?, status = ?, comment = ?
             WHERE id = ?
            """,
            (
                payload.date,
                payload.zone_id,
                payload.customer_name,
                payload.phone,
                payload.start_hour,
                end_hour,
                payload.status,
                payload.comment,
                booking_id,
            ),
        )
        row = c.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return Booking(**dict(row), duration=end_hour - payload.start_hour)


@app.delete("/api/bookings/{booking_id}")
def delete_booking(booking_id: int) -> dict[str, bool]:
    with closing(conn()) as c, c:
        deleted = c.execute("DELETE FROM bookings WHERE id = ?", (booking_id,)).rowcount
        if not deleted:
            raise HTTPException(404, "Бронь не найдена")
        return {"ok": True}


@app.get("/api/metrics")
def metrics(day: str = Query(..., alias="date")) -> dict[str, int]:
    with closing(conn()) as c:
        rows = c.execute("SELECT * FROM bookings WHERE date = ?", (day,)).fetchall()
        zones = {r["id"]: r["price_hour"] for r in c.execute("SELECT id, price_hour FROM zones").fetchall()}

    bookings_count = len(rows)
    occupied = sum(r["end_hour"] - r["start_hour"] for r in rows)
    load_pct = round((occupied / (10 * 18)) * 100) if rows else 0
    revenue = sum((r["end_hour"] - r["start_hour"]) * zones.get(r["zone_id"], 0) for r in rows)

    return {
        "bookings": bookings_count,
        "load_pct": load_pct,
        "revenue": revenue,
        "pending": sum(1 for r in rows if r["status"] == "pending"),
        "confirmed": sum(1 for r in rows if r["status"] == "confirmed"),
        "paid": sum(1 for r in rows if r["status"] == "paid"),
    }


@app.get("/api/bookings/export")
def export_csv(day: str = Query(..., alias="date")) -> Response:
    with closing(conn()) as c:
        rows = c.execute(
            "SELECT id, date, zone_id, customer_name, phone, start_hour, end_hour, status, comment FROM bookings WHERE date = ? ORDER BY start_hour, zone_id",
            (day,),
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "date", "zone_id", "customer_name", "phone", "start_hour", "end_hour", "status", "comment"])
    for r in rows:
        writer.writerow([r["id"], r["date"], r["zone_id"], r["customer_name"], r["phone"], r["start_hour"], r["end_hour"], r["status"], r["comment"]])

    filename = f"bookings-{day}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/", StaticFiles(directory=ROOT, html=True), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(ROOT / "index.html")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
