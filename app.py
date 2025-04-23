from flask import Flask, redirect, url_for, session, render_template, request, jsonify
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import os
import json 
import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"

DATA_FILE = 'data/finances.json'
os.makedirs('data', exist_ok=True)
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump([], f)

# Google OAuth Configuration
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
GOOGLE_CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar.readonly"
]

flow = Flow.from_client_secrets_file(
    GOOGLE_CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri="http://127.0.0.1:5000/callback"
)

# ---------------------------
# UTILITY FUNCTIONS
# ---------------------------
def load_transactions():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_transactions(transactions):
    with open(DATA_FILE, 'w') as f:
        json.dump(transactions, f, indent=4)

def calculate_summary(transactions):
    income = sum(float(t['amount']) for t in transactions if t['type'] == 'income')
    expense = sum(float(t['amount']) for t in transactions if t['type'] == 'expense')
    return {
        "income": income,
        "expense": expense,
        "balance": income - expense
    }

# ---------------------------
# ROUTES
# ---------------------------
@app.route("/")
def home():
    transactions = load_transactions()
    summary = calculate_summary(transactions)

    tasks = []
    events = []

    if "credentials" in session:
        credentials = Credentials.from_authorized_user_info(session["credentials"])

        if not credentials.valid:
            return redirect(url_for("login"))

        # Google Tasks
        tasks_service = build("tasks", "v1", credentials=credentials)
        task_lists = tasks_service.tasklists().list().execute()

        for task_list in task_lists.get("items", []):
            task_items = tasks_service.tasks().list(tasklist=task_list["id"]).execute().get("items", [])
            tasks.append({
                "name": task_list["title"],
                "id": task_list["id"],
                "tasks": task_items
            })

        # Google Calendar
        calendar_service = build("calendar", "v3", credentials=credentials)
        now = datetime.datetime.utcnow().isoformat() + "Z"
        page_token = None

        while True:
            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=now,
                singleEvents=True,
                orderBy='startTime',
                pageToken=page_token
            ).execute()

            events.extend(events_result.get('items', []))
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break

    return render_template("index.html", tasks=tasks, events=events, transactions=transactions, summary=summary, logged_in="credentials" in session)

@app.route('/')
def index():
    transactions = load_transactions()
    total_income = sum(float(t["amount"]) for t in transactions if t["type"] == "income")
    total_expense = sum(float(t["amount"]) for t in transactions if t["type"] == "expense")
    balance = total_income - total_expense
    return render_template('index.html', transactions=transactions, total_income=total_income, total_expense=total_expense, balance=balance)


@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    data = request.json
    transactions = load_transactions()
    transactions.append(data)
    save_transactions(transactions)

    # Calculate summary
    total_income = sum(float(t["amount"]) for t in transactions if t["type"] == "income")
    total_expense = sum(float(t["amount"]) for t in transactions if t["type"] == "expense")
    balance = total_income - total_expense

    return jsonify({
        'status': 'success',
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance
    })


@app.route("/login")
def login():
    session.clear()
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return redirect(auth_url)

@app.route("/callback")
def callback():
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    session["credentials"] = json.loads(credentials.to_json())
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/toggle_task", methods=["POST"])
def toggle_task():
    if "credentials" not in session:
        return redirect(url_for("login"))

    credentials = Credentials.from_authorized_user_info(session["credentials"])
    tasks_service = build("tasks", "v1", credentials=credentials)

    task_id = request.form.get("task_id")
    tasklist_id = request.form.get("tasklist_id")
    checked = request.form.get("status") == "on"

    if not task_id or not tasklist_id:
        return "Missing task ID or task list ID", 400

    task = tasks_service.tasks().get(tasklist=tasklist_id, task=task_id).execute()

    if checked:
        task["status"] = "completed"
        task["completed"] = datetime.datetime.utcnow().isoformat() + "Z"
    else:
        task["status"] = "needsAction"
        task.pop("completed", None)

    tasks_service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()

    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
