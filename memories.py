from pathlib import Path

from aiohttp import web

import sqlite3

import datetime
from calendar import monthrange


routes = web.RouteTableDef()


@routes.get("/")
async def index(request: web.Request) -> web.Response:
    return web.FileResponse(Path(__file__).parent / "index.html")


@routes.get("/api/names")
async def get_names(request: web.Request) -> web.Response:
    """(JSON) List of names memories are assigned to."""
    cur = request.app["db"].cursor()
    res = cur.execute("SELECT DISTINCT name FROM memories ORDER BY name")
    return web.json_response([n[0] for n in res.fetchall()])


@routes.get(r"/api/memories/{name}")
async def get_memories(request: web.Request) -> web.Response:
    """
    Enumerate existing memories for a given name.
    
    A (oldest-to-newest) list of objects as follows:
    
        {"id": 123, "date": "yyyy-mm-dd", "name": "...", "note": "..."}
    """
    cur = request.app["db"].cursor()
    
    res = cur.execute(
        "SELECT id, date, name, note FROM memories WHERE name = ? ORDER BY date, id",
        (request.match_info.get("name"), ),
    )
    
    out = [
        {
            "id": id,
            "date": date,
            "name": name,
            "note": note,
        }
        for id, date, name, note in res.fetchall()
    ]
    
    if out:
        dob = datetime.date.fromisoformat(out[0]["date"])
        
        for entry in out:
            now = datetime.date.fromisoformat(entry["date"])
            
            # Count number of months between two dates (disregarding days)
            year = dob.year
            month = dob.month
            delta_months = 0
            while year < now.year or month < now.month:
                delta_months += 1
                month += 1
                if month >= 13:
                  month -= 12
                  year += 1
            delta_years = delta_months // 12
            delta_months -= delta_years * 12
            
            # Compute differences in days and borrow months and years as
            # necessary
            delta_days = now.day - dob.day
            if delta_days < 0:
                delta_days += monthrange(dob.year, dob.month)[1]
                delta_months -= 1
            if delta_months < 0:
                delta_months += 12
                delta_years -= 1
            
            entry["days"] = delta_days
            entry["months"] = delta_months
            entry["years"] = delta_years
    
    return web.json_response(out)


@routes.post("/api/memories/{name}")
async def post_memory(request: web.Request) -> web.Response:
    """
    Add a new memory to the database.
    """
    data = await request.post()
    
    name = request.match_info["name"]
    date = data["date"]
    note = data["note"]
    
    cur = request.app["db"].cursor()
    res = cur.execute("INSERT INTO memories(date, name, note) VALUES(?, ?, ?)", (date, name, note))
    request.app["db"].commit()
    
    return web.json_response(cur.lastrowid)

routes.static("/static", Path(__file__).parent / "static")


async def database(app: web.Application):
    app["db"] = sqlite3.connect("memories.db")
    
    cur = app["db"].cursor()
    cur.execute(
        """
            CREATE TABLE IF NOT EXISTS memories(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name,
                date,
                note
            )
        """
    )
    app["db"].commit()
    
    yield
    
    app["db"].close()


app = web.Application()
app.add_routes(routes)
app.cleanup_ctx.append(database)


if __name__ == "__main__":
    web.run_app(app)
