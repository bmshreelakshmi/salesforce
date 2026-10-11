import os
import io
import csv
import sqlite3
from datetime import datetime
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    make_response
)

# ==================================================
# CONFIGURATION
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = BASE_DIR
FRONTEND_DIR = PROJECT_DIR
DATABASE = os.path.join(BASE_DIR, "events.db")

app = Flask(__name__)

# ==================================================
# DATABASE
# ==================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    # Events table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            participants INTEGER NOT NULL DEFAULT 1,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT 'Other',
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)

    # Settings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            admin_name TEXT NOT NULL DEFAULT 'Admin',
            email TEXT NOT NULL DEFAULT ''
        )
    """)

    # Fix existing settings database
    columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(settings)"
        ).fetchall()
    ]

    if "email" not in columns:
        conn.execute("""
            ALTER TABLE settings
            ADD COLUMN email TEXT NOT NULL DEFAULT ''
        """)

    if "admin_name" not in columns:
        conn.execute("""
            ALTER TABLE settings
            ADD COLUMN admin_name TEXT NOT NULL DEFAULT 'Admin'
        """)

    # Fix existing events database
    event_columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(events)"
        ).fetchall()
    ]

    required_columns = {
        "participants": "INTEGER NOT NULL DEFAULT 1",
        "location": "TEXT NOT NULL DEFAULT ''",
        "event_type": "TEXT NOT NULL DEFAULT 'Other'",
        "created_at": "TEXT NOT NULL DEFAULT ''"
    }

    for column, definition in required_columns.items():
        if column not in event_columns:
            conn.execute(
                f"ALTER TABLE events ADD COLUMN {column} {definition}"
            )

    conn.execute("""
        INSERT OR IGNORE INTO settings
        (id, admin_name, email)
        VALUES (1, 'Admin', '')
    """)

    conn.commit()
    conn.close()


def get_events():
    conn = get_db()

    rows = conn.execute("""
        SELECT * FROM events
        ORDER BY date ASC, time ASC
    """).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_settings():
    conn = get_db()

    row = conn.execute("""
        SELECT * FROM settings WHERE id = 1
    """).fetchone()

    conn.close()

    return dict(row) if row else {
        "admin_name": "Admin",
        "email": ""
    }


def get_analytics():
    events = get_events()
    today = datetime.now().date().isoformat()

    upcoming = 0
    completed = 0
    types = {}

    for event in events:
        if event["date"] >= today:
            upcoming += 1
        else:
            completed += 1

        kind = event["event_type"] or "Other"
        types[kind] = types.get(kind, 0) + 1

    return {
        "total_events": len(events),
        "upcoming_events": upcoming,
        "completed_events": completed,
        "ai_plans_generated": 0,
        "events_by_type": types
    }


# ==================================================
# FRONTEND PAGES
# ==================================================

@app.route("/")
def dashboard():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/create-event")
def create_event_page():
    return send_from_directory(
        FRONTEND_DIR, "create-event.html"
    )


@app.route("/my-events")
def my_events_page():
    return send_from_directory(
        FRONTEND_DIR, "my-events.html"
    )


@app.route("/ai-agent")
def ai_agent_page():
    return send_from_directory(
        FRONTEND_DIR, "ai-agent.html"
    )


# Serve frontend assets
@app.route("/frontend/<path:filename>")
def frontend_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ==================================================
# CREATE EVENT
# ==================================================

@app.route("/api/events", methods=["GET", "POST"])
def events_api():

    if request.method == "GET":
        return jsonify(get_events())

    data = request.get_json(silent=True)

    if not data:
        data = request.form.to_dict()

    name = str(
        data.get("name", data.get("event_name", ""))
    ).strip()

    participants = data.get("participants", 1)

    event_date = str(
        data.get("date", data.get("event_date", ""))
    ).strip()

    event_time = str(
        data.get("time", data.get("event_time", ""))
    ).strip()

    location = str(data.get("location", "")).strip()

    event_type = str(
        data.get("event_type", data.get("type", "Other"))
    ).strip() or "Other"

    if not name or not event_date or not event_time:
        return jsonify({
            "success": False,
            "message": "Event name, date and time are required."
        }), 400

    try:
        participants = int(participants)

        if participants < 1:
            raise ValueError

        parsed_date = datetime.strptime(
            event_date, "%Y-%m-%d"
        ).date()

        datetime.strptime(event_time, "%H:%M")

    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Please enter valid participants, date and time."
        }), 400

    if parsed_date < datetime.now().date():
        return jsonify({
            "success": False,
            "message": "Event date cannot be in the past."
        }), 400

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO events (
            name, participants, date, time,
            location, event_type, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        participants,
        event_date,
        event_time,
        location,
        event_type,
        datetime.now().isoformat(timespec="seconds")
    ))

    event_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Event created successfully!",
        "event_id": event_id
    }), 201


# ==================================================
# GET ONE EVENT
# ==================================================

@app.route("/api/events/<int:event_id>", methods=["GET"])
def get_one_event(event_id):
    conn = get_db()

    event = conn.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,)
    ).fetchone()

    conn.close()

    if not event:
        return jsonify({
            "success": False,
            "message": "Event not found."
        }), 404

    return jsonify(dict(event))


# ==================================================
# UPDATE EVENT
# ==================================================

@app.route("/api/events/<int:event_id>", methods=["PUT"])
def update_event(event_id):
    data = request.get_json(silent=True) or {}

    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,)
    ).fetchone()

    if not existing:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Event not found."
        }), 404

    name = str(data.get("name", existing["name"])).strip()
    date = str(data.get("date", existing["date"])).strip()
    time = str(data.get("time", existing["time"])).strip()
    location = str(data.get("location", existing["location"])).strip()
    event_type = str(
        data.get("event_type", existing["event_type"])
    ).strip()

    try:
        participants = int(
            data.get("participants", existing["participants"])
        )
        datetime.strptime(date, "%Y-%m-%d")
        datetime.strptime(time, "%H:%M")

        if participants < 1 or not name:
            raise ValueError

    except (ValueError, TypeError):
        conn.close()
        return jsonify({
            "success": False,
            "message": "Invalid event information."
        }), 400

    conn.execute("""
        UPDATE events
        SET name = ?, participants = ?, date = ?,
            time = ?, location = ?, event_type = ?
        WHERE id = ?
    """, (
        name, participants, date, time,
        location, event_type, event_id
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Event updated successfully."
    })


# ==================================================
# DELETE EVENT
# ==================================================

@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    conn = get_db()

    cursor = conn.execute(
        "DELETE FROM events WHERE id = ?",
        (event_id,)
    )

    conn.commit()
    deleted = cursor.rowcount
    conn.close()

    if deleted == 0:
        return jsonify({
            "success": False,
            "message": "Event not found."
        }), 404

    return jsonify({
        "success": True,
        "message": "Event deleted successfully."
    })


# ==================================================
# CSV DOWNLOAD
# ==================================================

@app.route("/api/events/export/csv", methods=["GET"])
def export_events_csv():
    events = get_events()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Event Name", "Participants",
        "Date", "Time", "Location",
        "Event Type", "Created At"
    ])

    for event in events:
        writer.writerow([
            event["id"],
            event["name"],
            event["participants"],
            event["date"],
            event["time"],
            event["location"],
            event["event_type"],
            event["created_at"]
        ])

    response = make_response(
        "\ufeff" + output.getvalue()
    )

    response.headers["Content-Type"] = (
        "text/csv; charset=utf-8"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=all_events.csv"
    )

    return response


# ==================================================
# ANALYTICS
# ==================================================

@app.route("/api/analytics", methods=["GET"])
def analytics_api():
    return jsonify(get_analytics())


# ==================================================
# SETTINGS
# ==================================================

@app.route("/api/settings", methods=["GET", "POST", "PUT"])
def settings_api():

    if request.method == "GET":
        return jsonify(get_settings())

    data = request.get_json(silent=True)

    if not data:
        data = request.form.to_dict()

    admin_name = str(
        data.get("admin_name", "")
    ).strip()

    email = str(data.get("email", "")).strip()

    if not admin_name or not email:
        return jsonify({
            "success": False,
            "message": "Admin name and email are required."
        }), 400

    conn = get_db()

    conn.execute("""
        UPDATE settings
        SET admin_name = ?, email = ?
        WHERE id = 1
    """, (admin_name, email))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Settings saved successfully."
    })


# ==================================================
# AI EVENT AGENT
# ==================================================

@app.route("/api/ai-agent", methods=["POST"])
def ai_agent_api():

    data = request.get_json(silent=True) or {}

    question = str(
        data.get("question", data.get("message", ""))
    ).strip()

    if not question:
        return jsonify({
            "success": False,
            "message": "Please enter your event planning question."
        }), 400

    q = question.lower()

    if "budget" in q:
        answer = """
EVENT BUDGET PLAN

Venue: 30%
Food and refreshments: 25%
Decoration: 15%
Marketing: 10%
Equipment: 10%
Emergency reserve: 10%

Adjust the percentages according to your budget.
"""

    elif "wedding" in q:
        answer = """
WEDDING PLANNING CHECKLIST

1. Select date and venue.
2. Prepare guest list.
3. Arrange catering and decoration.
4. Book photography and entertainment.
5. Prepare the event schedule.
6. Keep a backup plan.
"""

    elif "conference" in q:
        answer = """
CONFERENCE PLANNING CHECKLIST

1. Define objectives.
2. Book a venue.
3. Invite speakers.
4. Arrange registration.
5. Prepare presentation equipment.
6. Create a session schedule.
"""

    elif "birthday" in q:
        answer = """
BIRTHDAY EVENT PLAN

1. Prepare the guest list.
2. Select a venue.
3. Arrange cake and food.
4. Plan decorations.
5. Organize games and entertainment.
6. Prepare a schedule.
"""

    else:
        answer = """
EVENT PLANNING SUGGESTIONS

1. Define the event objective.
2. Set a budget.
3. Select date and venue.
4. Estimate participants.
5. Arrange food and equipment.
6. Assign tasks.
7. Create an event timeline.
8. Prepare a backup plan.
9. Collect feedback after the event.
"""

    return jsonify({
        "success": True,
        "question": question,
        "answer": answer,
        "mode": "demo"
    })


# ==================================================
# DASHBOARD SUMMARY
# ==================================================

@app.route("/api/dashboard", methods=["GET"])
def dashboard_api():
    return jsonify({
        **get_analytics(),
        "admin": get_settings()
    })


# ==================================================
# HEALTH CHECK
# ==================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "application": "Salesforce AI Event Manager"
    })


# ==================================================
# INITIALIZE DATABASE AND START APP
# ==================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5001)),
        debug=True
    )
