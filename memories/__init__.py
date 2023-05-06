from typing import Any, NamedTuple

from pathlib import Path

from collections import OrderedDict

from aiohttp import web

import re

import jinja2

import sqlite3

import datetime
from calendar import monthrange


routes = web.RouteTableDef()


def render_template(
    request: web.Request, template: str, variables: dict[str, Any] = {}
) -> web.Response:
    """
    Render a Jinja2 template.
    """
    static = ("../" * (request.url.path.count("/") - 1)) + "static"

    template = request.app["env"].get_template(template)
    page = template.render(static=static, **variables)

    return web.Response(body=page, content_type="text/html")


@routes.get("/")
async def index(request: web.Request) -> web.Response:
    cur = request.app["db"].cursor()
    res = cur.execute("SELECT DISTINCT name FROM memories ORDER BY name")
    names = [n[0] for n in res.fetchall()]

    return render_template(request, "index.html", {"names": names})


class DateDelta(NamedTuple):
    years: int
    months: int
    days: int


def date_delta(before: datetime.date, after: datetime.date) -> DateDelta:
    """
    Return the difference between two dates in terms of calendar years, months
    and days.
    """
    delta_months = ((after.year * 12) + after.month) - (
        (before.year * 12) + before.month
    )
    delta_years = delta_months // 12
    delta_months -= delta_years * 12

    delta_days = after.day - before.day
    if delta_days < 0:
        delta_days += monthrange(before.year, before.month)[1]
        delta_months -= 1
    if delta_months < 0:
        delta_months += 12
        delta_years -= 1

    return DateDelta(delta_years, delta_months, delta_days)


class Memory(NamedTuple):
    id: int
    date: str
    name: str
    age: DateDelta
    note: str


def get_memories(cur: sqlite3.Cursor, name: str) -> list[Memory]:
    res = cur.execute(
        "SELECT id, date, note FROM memories WHERE name = ? ORDER BY date, id",
        (name,),
    ).fetchall()

    if len(res) == 0:
        return []

    # Assume DoB is the date of the first memory
    dob = datetime.date.fromisoformat(res[0][1])

    return [
        Memory(
            id=id,
            date=date,
            name=name,
            age=date_delta(dob, datetime.date.fromisoformat(date)),
            note=note,
        )
        for id, date, note in res
    ]


def get_memory(cur: sqlite3.Cursor, id: int) -> list[Memory]:
    date, name, note = cur.execute(
        "SELECT date, name, note FROM memories WHERE id = ?",
        (id,),
    ).fetchone()

    (dob,) = cur.execute(
        "SELECT date FROM memories WHERE name = ? ORDER BY date, id LIMIT 1",
        (name,),
    ).fetchone()

    return Memory(
        id=id,
        date=date,
        name=name,
        age=date_delta(
            datetime.date.fromisoformat(dob), datetime.date.fromisoformat(date)
        ),
        note=note,
    )


def group_memories(
    memories: list[Memory],
) -> OrderedDict[tuple[int, int], list[Memory]]:
    """
    Group memories by ages quantised to (year, month).
    """
    memories_by_month = OrderedDict()

    last_age_months = None
    memories_this_month = None
    for memory in memories:
        age_months = (memory.age.years, memory.age.months)
        if age_months != last_age_months:
            memories_by_month[age_months] = memories_this_month = []
            last_age_months = age_months

        memories_this_month.append(memory)

    return memories_by_month


def format_years_months(age: tuple[int, int]) -> str:
    """
    Format an age given as a tuple (years, months) as a string like "3 years, 1
    month".
    """
    years, months = age[:2]

    if years == 0 and months == 0:
        return "newborn"
    elif years == 0:
        return f"{months} month{'s' if months != 1 else ''}"
    elif months == 0:
        return f"{years} year{'s' if years != 1 else ''}"
    else:
        return (
            f"{years} year{'s' if years != 1 else ''}, "
            f"{months} month{'s' if months != 1 else ''}"
        )


@routes.get("/memories/{name}")
async def memories(request: web.Request) -> web.Response:
    name = request.match_info["name"]

    variables = {
        "name": name,
        "today": datetime.date.today().isoformat(),
        "memories_by_month": group_memories(
            get_memories(request.app["db"].cursor(), name)
        ),
    }

    response = render_template(request, "memories.html", variables)
    if "id" in request.query:
        response.headers["x-id"] = request.query["id"]
    return response


@routes.post("/memories/{name}")
async def post_memories(request: web.Request) -> web.Response:
    """
    POSTing to this endpoint will either insert, modify or delete a memory
    depending on whether 'id' is absent (insert) or present (edit) or the
    only value (delete).
    """
    data = await request.post()

    name = request.match_info["name"]
    id = data.get("id")  # None iff creating a new memory

    if "date" in data and "note" in data:
        # Create or edit
        date = data["date"]
        note = data["note"]

        # Simple validation
        if not name.strip():
            raise web.HTTPBadRequest(text="Name was empty.")
        if not re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
            raise web.HTTPBadRequest(
                text=f"Invalid date: {date!r}, expected YYYY-MM-DD"
            )
        if not note.strip():
            raise web.HTTPBadRequest(text="Note was empty.")

        cur = request.app["db"].cursor()

        if id is None:
            res = cur.execute(
                "INSERT INTO memories(date, name, note) VALUES(?, ?, ?)",
                (date, name, note),
            )
            id = cur.lastrowid
        else:
            res = cur.execute(
                "UPDATE memories SET date = ?, note = ? WHERE id = ?", (date, note, id)
            )

        request.app["db"].commit()

        raise web.HTTPSeeOther(f"memories/{name}?id={id}#memory-{id}")
    elif id is not None:
        # Delete
        cur = request.app["db"].cursor()
        memory = get_memory(cur, id)

        cur.execute("DELETE FROM memories WHERE id = ?", (id,))
        request.app["db"].commit()

        raise web.HTTPSeeOther(
            f"memories/{name}#age-{memory.age.years}-{memory.age.months}"
        )


@routes.get(r"/edit/{id:\d+}")
async def memories(request: web.Request) -> web.Response:
    id = request.match_info["id"]

    variables = {
        "memory": get_memory(request.app["db"].cursor(), id),
        "hx_request": "HX-Request" in request.headers,
    }

    return render_template(request, "edit.html", variables)


routes.static("/static", Path(__file__).parent / "static")


def make_app(db_filename: Path) -> web.Application:
    app = web.Application()
    app.add_routes(routes)

    @app.cleanup_ctx.append
    async def db(app: web.Application):
        app["db"] = sqlite3.connect(db_filename)

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

        try:
            yield
        finally:
            app["db"].close()

    @app.on_startup.append
    async def env(app: web.Application):
        app["env"] = jinja2.Environment(
            loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
            autoescape=jinja2.select_autoescape(),
        )

        app["env"].filters["format_years_months"] = format_years_months

    return app


def main() -> None:
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    web.run_app(make_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
