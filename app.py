from flask import Flask, redirect, url_for, session, render_template, request, jsonify
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import os
import json 
import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"
transactions = []


# Google OAuth Configuration
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GOOGLE_CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/tasks",  # Full access to Google Tasks
    "https://www.googleapis.com/auth/calendar.readonly"  # Read-only access to Calendar
]


flow = Flow.from_client_secrets_file(
    GOOGLE_CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri="http://127.0.0.1:5000/callback"
)

@app.route("/")
def home():
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
            task_list_id = task_list["id"]
            task_list_name = task_list["title"]
            task_items = tasks_service.tasks().list(tasklist=task_list_id).execute().get("items", [])
            tasks.append({
                "name": task_list_name,
                "id": task_list_id,
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
    
    return render_template("index.html", tasks=tasks, events=events, logged_in="credentials" in session)


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

@app.route('/')
def index():
    return render_template('index.html', transactions=transactions)

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    data = request.get_json()
    description = data.get('description')
    amount = float(data.get('amount'))
    trans_type = data.get('type')

    if not description or not amount or trans_type not in ['income', 'expense']:
        return jsonify({'error': 'Invalid input'}), 400

    transaction = {
        'description': description,
        'amount': amount,
        'type': trans_type
    }

    transactions.append(transaction)
    return jsonify({'success': True, 'transaction': transaction})

@app.route('/get_transactions', methods=['GET'])
def get_transactions():
    return jsonify(transactions)

@app.route('/delete_transaction', methods=['POST'])
def delete_transaction():
    data = request.get_json()
    index = data.get('index')

    if index is not None and 0 <= index < len(transactions):
        deleted = transactions.pop(index)
        return jsonify({'success': True, 'deleted': deleted})
    return jsonify({'error': 'Invalid index'}), 400

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
