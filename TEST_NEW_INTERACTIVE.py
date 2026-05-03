import asyncio
import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase
import av
import cv2
import os
import pandas as pd
import numpy as np
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import time
import psycopg2
from supabase import create_client

# --- 1. CONFIG & AUTH SETTINGS ---
st.set_page_config(page_title="NEURAL HR OS 2026", layout="wide", page_icon="🛡️")

# Constants
PASS_FILE = "security.txt"
MASTER_KEY = "MASTER2026"
VIDEO_PATH = "background.mp4"  # Ensure this file exists in your project folder

if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("admin123")

# Initialize Cooldown for Email to prevent spamming
if "last_email_time" not in st.session_state:
    st.session_state.last_email_time = datetime.now() - timedelta(minutes=5)

# Supabase init
try:
    supabase = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
except:
    pass


def get_db_connection():
    return psycopg2.connect(st.secrets["postgres"]["url"])


def send_security_notification(subject, body):
    # Cooldown check: send only one email every 2 minutes for the same alert
    if datetime.now() - st.session_state.last_email_time > timedelta(minutes=2):
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'], msg['To'] = "mohamedauoup@gmail.com", "mohamedauoup@gmail.com"
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login("mohamedauoup@gmail.com", "xjpwurhrozvybini")
                server.send_message(msg)
            st.session_state.last_email_time = datetime.now()
        except Exception as e:
            pass


def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY, first_name TEXT, last_name TEXT, dept_name TEXT, 
            address TEXT, shift_start TEXT, phone TEXT, salary REAL, is_active INTEGER DEFAULT 1)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY, emp_id INTEGER, name TEXT, date TEXT, clock_in TEXT, clock_out TEXT)''')
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass


init_db()


# --- 2. TRANSFORMERS ---

class FaceRecognitionTransformer(VideoProcessorBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            for (x, y, w, h) in faces:
                # Logic: Check status of employees
                cur.execute("SELECT first_name, is_active FROM employees LIMIT 1")
                res = cur.fetchone()
                if res:
                    name, active = res
                    color = (0, 255, 0) if active == 1 else (0, 0, 255)
                    status = "ACTIVE" if active == 1 else "TERMINATED"

                    if active == 0:
                        # Security Alert Email Logic
                        send_security_notification("SECURITY ALERT",
                                                   f"Terminated person {name} detected at {datetime.now()}")

                    cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(img, f"{name} - {status}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            cur.close()
            conn.close()
        except:
            for (x, y, w, h) in faces:
                cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 0), 2)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


class EnrollmentTransformer(VideoProcessorBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
            cv2.putText(img, "SCANNING FEATURES...", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")


# --- 3. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "res" not in st.session_state: st.session_state.res = None
if "enroll_step" not in st.session_state: st.session_state.enroll_step = 1

if not st.session_state.authenticated:
    # --- MP4 Background/Header Section ---
    if os.path.exists(VIDEO_PATH):
        st.video(VIDEO_PATH, loop=True, autoplay=True, muted=True)

    col = st.columns([1, 1.5, 1])[1]
    with col:
        st.title("🛡️ NEURAL HR OS 2026")
        pwd = st.text_input("HR Security Password", type="password")

        with st.expander("🔐 Password Management"):
            mk = st.text_input("Enter Master Key", type="password")
            npwd = st.text_input("Enter New Password", type="password")
            if st.button("RESET PASSWORD"):
                if not mk or not npwd:
                    st.error("⚠️ Both Master Key and New Password must be entered!")
                elif mk == MASTER_KEY:
                    with open(PASS_FILE, "w") as f:
                        f.write(npwd)
                    st.success("✅ Password Updated!");
                    time.sleep(1);
                    st.rerun()
                else:
                    st.error("❌ Invalid Master Key")

        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip():
                    st.session_state.authenticated = True
                    send_security_notification("Access Alert",
                                               "System accessed at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    st.rerun()
                else:
                    st.error("Access Denied")
else:
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
        st.write(f"Logged in: Admin")
        if st.button("🔒 LOCK CONSOLE"):
            st.session_state.authenticated = False
            st.rerun()
        menu = st.radio("System Modules", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL",
                                           "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    rtc_config = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

    if menu == "📺 LIVE VISION":
        st.subheader("Neural Recognition Feed")
        webrtc_streamer(
            key="vision",
            video_processor_factory=FaceRecognitionTransformer,
            media_stream_constraints={"video": True, "audio": False},
            rtc_configuration=rtc_config
        )

    elif menu == "🔍 SEARCH BY ID":
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM employees WHERE id=%s", conn, params=(sid,))
            st.dataframe(df)
            conn.close()

    elif menu == "➕ ENROLL USER":
        st.subheader("Employee Enrollment Pipeline")

        step_cols = st.columns(2)
        if st.session_state.enroll_step == 1:
            with step_cols[0]:
                st.info("Step 1: Feature Scanning")
                webrtc_streamer(key="enroll_scan", video_processor_factory=EnrollmentTransformer,
                                rtc_configuration=rtc_config)
                if st.button("NEXT: CAPTURE PHOTO ➡️"):
                    st.session_state.enroll_step = 2
                    st.rerun()

        else:
            with step_cols[0]:
                st.info("Step 2: Take Official Photo")
                img_file = st.camera_input("Capture Face")
                if st.button("⬅️ BACK TO SCAN"):
                    st.session_state.enroll_step = 1
                    st.rerun()

            with step_cols[1]:
                with st.form("enroll_form"):
                    fn = st.text_input("First Name")
                    ln = st.text_input("Last Name")
                    dept = st.text_input("Department")
                    if st.form_submit_button("✨ COMMIT TO DATABASE"):
                        if fn and ln:
                            conn = get_db_connection()
                            cur = conn.cursor()
                            cur.execute("INSERT INTO employees (first_name, last_name, dept_name) VALUES (%s, %s, %s)",
                                        (fn, ln, dept))
                            conn.commit();
                            cur.close();
                            conn.close()
                            st.success("✅ Employee enrolled successfully!");
                            st.balloons()
                            st.session_state.enroll_step = 1
                        else:
                            st.error("Names are required")

    elif menu == "📝 MODIFY PERSONNEL":
        mid = st.number_input("Target ID", min_value=1)
        if st.button("FETCH PROFILE"):
            conn = get_db_connection();
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id=%s", (mid,))
            st.session_state['res'] = cur.fetchone()
            conn.close()

        if st.session_state['res']:
            with st.form("mod_form"):
                n_fn = st.text_input("First Name", value=st.session_state['res'][1])
                if st.form_submit_button("💾 OVERWRITE"):
                    conn = get_db_connection();
                    cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s WHERE id=%s", (n_fn, mid))
                    conn.commit();
                    cur.close();
                    conn.close()
                    st.success("✅ Profile updated!");
                    st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        st.subheader("Access Control Toggle")
        tid = st.number_input("Enter Employee ID to Toggle Access", min_value=1)
        if st.button("TOGGLE STATUS"):
            conn = get_db_connection();
            cur = conn.cursor()
            # Check current status
            cur.execute("SELECT is_active, first_name FROM employees WHERE id=%s", (tid,))
            record = cur.fetchone()
            if record:
                new_status = 0 if record[0] == 1 else 1
                cur.execute("UPDATE employees SET is_active=%s WHERE id=%s", (new_status, tid))
                conn.commit()
                status_text = "TERMINATED" if new_status == 0 else "REACTIVATED"
                st.warning(f"⚠️ Access for {record[1]} has been {status_text}")
            else:
                st.error("ID not found")
            cur.close();
            conn.close()


    elif menu == "📂 STAFF DIRECTORY":

        conn = get_db_connection()

        df = pd.read_sql_query("SELECT id, first_name, last_name, dept_name, is_active FROM employees", conn)

        conn.close()

        # Define color logic using column_config

        st.dataframe(

            df,

            column_config={

                "is_active": st.column_config.NumberColumn(

                    "Status",

                    help="1 = Active, 0 = Terminated",

                    format="%d",

                )

            },

            hide_index=True

        )

        # If you specifically want to see colored text/backgrounds in the UI:

        st.write("### Color Legend")

        st.markdown(":green[Green] = Active | :red[Red] = Terminated")
        
    elif menu == "📊 DAILY REPORTS":
        if st.button("🚨 DELETE ALL DATA"):
            conn = get_db_connection();
            cur = conn.cursor()
            cur.execute("DELETE FROM employees");
            cur.execute("DELETE FROM attendance")
            conn.commit();
            conn.close();
            st.error("Data Wiped")

        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM attendance", conn)
        st.dataframe(df);
        conn.close()
