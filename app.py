"""
Daily Work Management System - Single-file Streamlit app
Save this file as `app.py` and run `streamlit run app.py`.

Features:
- User registration and login (local sqlite, passwords hashed)
- Add daily tasks with title, description, optional time
- Mark tasks as Done / Pending
- Pending bucket shows tasks still pending with the datetime they became pending
- History view shows tasks per day (Done & Pending at end of day)
- Export history as CSV

Notes:
- For demo/local use only. For production, use proper password hashing (bcrypt), email verification, HTTPS, etc.

"""

import streamlit as st
import sqlite3
from datetime import datetime, date
import hashlib
import pandas as pd
import os
import pytz


# ----------------------------
# Database helpers
# ----------------------------
DB_PATH = "tasks.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    # tasks table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            task_date TEXT NOT NULL, -- date for which task was added (YYYY-MM-DD)
            task_time TEXT, -- optional time
            status TEXT NOT NULL, -- pending / done
            status_changed_at TEXT NOT NULL,
            pending_from TEXT, -- when it became pending (datetime)
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    return conn

# ----------------------------
# Auth helpers
# ----------------------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username: str, password: str) -> (bool, str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
                    (username, hash_password(password), datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return True, "Registered successfully"
    except sqlite3.IntegrityError:
        return False, "Username already taken"

def login_user(username: str, password: str) -> (bool, dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE username = ?', (username,))
    row = cur.fetchone()
    if not row:
        return False, None
    if row['password_hash'] != hash_password(password):
        return False, None
    user = dict(row)
    return True, user

# ----------------------------
# Task helpers
# ----------------------------

def add_task(user_id: int, title: str, description: str, task_date: str, task_time: str | None):
    conn = get_conn()
    cur = conn.cursor()
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')

    cur.execute('''INSERT INTO tasks (user_id, title, description, created_at, task_date, task_time, status, status_changed_at, pending_from)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, title, description, now, task_date, task_time or '', 'pending', now, now))
    conn.commit()

def get_tasks_for_date(user_id: int, task_date: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM tasks WHERE user_id = ? AND task_date = ? ORDER BY id', (user_id, task_date))
    return [dict(r) for r in cur.fetchall()]

def get_pending_tasks(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY task_date, task_time", (user_id,))
    return [dict(r) for r in cur.fetchall()]

def change_task_status(task_id: int, new_status: str):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')


    if new_status == 'pending':
        pending_from = now
    else:
        pending_from = None
    cur.execute('UPDATE tasks SET status = ?, status_changed_at = ?, pending_from = ? WHERE id = ?',
                (new_status, now, pending_from, task_id))
    conn.commit()

def get_history(user_id: int, start_date: str | None = None, end_date: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    query = 'SELECT * FROM tasks WHERE user_id = ?'
    params = [user_id]
    if start_date:
        query += ' AND task_date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND task_date <= ?'
        params.append(end_date)
    query += ' ORDER BY task_date DESC, task_time'
    cur.execute(query, params)
    return [dict(r) for r in cur.fetchall()]

# ----------------------------
# UI
# ----------------------------

st.set_page_config(page_title="Daily Work Management", page_icon="🗂️")
init_db()

# session state for auth
if 'user' not in st.session_state:
    st.session_state.user = None

st.title("Daily Work Management System")

# Sidebar: auth and navigation
with st.sidebar:
    st.header("Account")
    if st.session_state.user is None:
        auth_mode = st.radio("Choose", ["Login", "Register"], index=0)
        username = st.text_input("Username", key='auth_user')
        password = st.text_input("Password", type='password', key='auth_pass')
        if auth_mode == 'Register':
            if st.button("Register"):
                ok, msg = register_user(username.strip(), password)
                st.info(msg)
        else:
            if st.button("Login"):
                ok, user = login_user(username.strip(), password)
                if ok:
                    st.session_state.user = user
                    st.success(f"Logged in as {user['username']}")
                else:
                    st.error("Login failed. Check username/password")
    else:
        st.write(f"Logged in as: **{st.session_state.user['username']}**")
        if st.button("Logout"):
            st.session_state.user = None
            st.experimental_rerun()

    st.header("Navigate")
    page = st.selectbox("Go to", ["Add Task", "Today", "Pending Bucket", "History", "Export CSV"]) 

# If not logged in, block pages
if st.session_state.user is None:
    st.info("Please register or login from the sidebar to use the app")
    st.stop()

user = st.session_state.user
user_id = user['id']

# ----------------------------
# Pages
# ----------------------------

if page == 'Add Task':
    st.header("Add Task")
    with st.form('add_task'):
        title = st.text_input('Task title')
        description = st.text_area('Description (optional)')
        # default task date is today in user's local date
        task_date = st.date_input('For date', value=date.today())
        task_time = st.time_input('Optional time', value=None)
        submitted = st.form_submit_button('Add Task')
        if submitted:
            if not title.strip():
                st.error('Please provide a task title')
            else:
                ttime = task_time.strftime('%H:%M') if task_time else ''
                add_task(user_id, title.strip(), description.strip(), task_date.isoformat(), ttime)
                st.success('Task added')

elif page == 'Today':
    st.header("Tasks for a Day")
    chosen_date = st.date_input('Choose date', value=date.today())
    tasks = get_tasks_for_date(user_id, chosen_date.isoformat())
    if not tasks:
        st.info('No tasks for this date')
    else:
        for t in tasks:
            st.markdown(f"**{t['title']}**  ")
            if t['description']:
                st.write(t['description'])
            cols = st.columns([1,1,4])
            with cols[0]:
                st.write(f"Status: **{t['status']}**")
            with cols[1]:
                if t['status'] == 'pending':
                    if st.button('Mark Done', key=f"done_{t['id']}"):
                        change_task_status(t['id'], 'done')
                        st.experimental_rerun()
                else:
                    if st.button('Mark Pending', key=f"pending_{t['id']}"):
                        change_task_status(t['id'], 'pending')
                        st.experimental_rerun()
            with cols[2]:
                # Format created_at for display
                try:
                    added_dt = datetime.fromisoformat(t['created_at'])
                    added_str = added_dt.strftime('%d-%m-%Y %I:%M %p')
                except:
                    added_str = t['created_at']

                st.write(f"Added: {added_str}")
                st.write(f"Time: {t['task_time']}")

elif page == 'Pending Bucket':
    st.header('Pending Bucket')
    pend = get_pending_tasks(user_id)
    if not pend:
        st.success('No pending tasks. Nice!')
    else:
        for p in pend:
            pending_from = p['pending_from'] or p['created_at']
            # calculate duration in human readable
            try:
                dt = datetime.fromisoformat(pending_from)
                delta = datetime.utcnow() - dt
                days = delta.days
                hours = delta.seconds // 3600
                mins = (delta.seconds % 3600) // 60
                since = f"{days}d {hours}h {mins}m ago"
            except Exception:
                since = pending_from
            st.markdown(f"**{p['title']}** — {p['task_date']} {p['task_time']} — Pending since: {since}")
            if p['description']:
                st.write(p['description'])
            if st.button('Mark Done', key=f"pend_done_{p['id']}"):
                change_task_status(p['id'], 'done')
                st.experimental_rerun()

elif page == 'History':
    st.header('History')
    col1, col2 = st.columns(2)
    with col1:
        sdate = st.date_input('Start date', value=date.today().replace(day=1))
    with col2:
        edate = st.date_input('End date', value=date.today())
    hist = get_history(user_id, sdate.isoformat(), edate.isoformat())
    if not hist:
        st.info('No history in this range')
    else:
        df = pd.DataFrame(hist)
        # show selected columns
        display_df = df[['task_date','task_time','title','description','status','status_changed_at']]
        st.dataframe(display_df)
        if st.button('Show day-wise summary'):
            summary = display_df.groupby('task_date').agg(
                total_tasks=('title','count'),
                done=('status', lambda s: (s=='done').sum()),
                pending=('status', lambda s: (s=='pending').sum())
            ).reset_index()
            st.dataframe(summary)

elif page == 'Export CSV':
    st.header('Export History as CSV')
    sdate = st.date_input('Start date', value=date.today().replace(day=1))
    edate = st.date_input('End date', value=date.today())
    hist = get_history(user_id, sdate.isoformat(), edate.isoformat())
    if not hist:
        st.info('No data to export')
    else:
        df = pd.DataFrame(hist)
        csv = df.to_csv(index=False)
        st.download_button('Download CSV', csv, file_name=f'history_{sdate}_{edate}.csv')

# Footer
st.write('---')
st.caption('This is a simple demo. For production use, upgrade security, and consider external DB.')
