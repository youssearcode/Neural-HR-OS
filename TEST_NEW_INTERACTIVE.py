1.mp4import asyncio
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
VIDEO_PATH = "1.mp4"

if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("admin123")

if "last_email_time" not in st.session_state:
    st.session_state.last_email_time = datetime.now() - timedelta(minutes=5)

try:
    supabase = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
except:
    pass

def get_db_connection():
    return psycopg2.connect(st.secrets["postgres"]["url"])

def send_security_notification(subject, body):
    if datetime.now() - st.session_state.last_email_time > timedelta(minutes=2):
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'], msg['To'] = "mohamedauoup@gmail.com", "mohamedauoup@gmail.com"
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login("mohamedauoup@gmail.com", "xjpwurhrozvybini")
                server.send_message(msg)
            st.session_state.last_email_time = datetime.now()
        except: pass

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY, first_name TEXT, last_name TEXT, dept_name TEXT, 
            job_title TEXT, national_id TEXT, dob TEXT, hire_date TEXT, 
            phone TEXT, emergency_contact TEXT, blood_type TEXT, branch TEXT, 
            access_level INTEGER, is_active INTEGER DEFAULT 1)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY, emp_id INTEGER, name TEXT, date TEXT, clock_in TEXT, clock_out TEXT)''')
        conn.commit()
        cur.close()
        conn.close()
    except: pass

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
                cur.execute("SELECT first_name, is_active FROM employees LIMIT 1")
                res = cur.fetchone()
                if res:
                    name, active = res
                    color = (0, 255, 0) if active == 1 else (0, 0, 255)
                    status = "ACTIVE" if active == 1 else "TERMINATED"
                    if active == 0: send_security_notification("SECURITY ALERT", f"Terminated {name} detected!")
                    cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(img, f"{name}-{status}", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            cur.close(); conn.close()
        except: pass
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
            cv2.putText(img, "SCANNING...", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- 3. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "res" not in st.session_state: st.session_state.res = None
if "enroll_step" not in st.session_state: st.session_state.enroll_step = 1

if not st.session_state.authenticated:
    if os.path.exists(VIDEO_PATH): st.video(VIDEO_PATH, loop=True, autoplay=True, muted=True)
    col = st.columns([1, 1.5, 1])[1]
    with col:
        st.title("🛡️ NEURAL HR OS 2026")
        pwd = st.text_input("HR Security Password", type="password")
        with st.expander("🔐 Password Management"):
            mk = st.text_input("Master Key", type="password")
            npwd = st.text_input("New Password", type="password")
            if st.button("RESET PASSWORD"):
                if not mk or not npwd:
                    st.error("Error: Both Master Key and New Password required.")
                    send_security_notification("Security Warning", "Incomplete password reset attempt.")
                elif mk == MASTER_KEY:
                    with open(PASS_FILE, "w") as f: f.write(npwd)
                    st.success("Password Updated!"); st.rerun()
                else:
                    st.error("Invalid Master Key.")
                    send_security_notification("Security Alert", "Unauthorized password reset attempt.")
        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip():
                    st.session_state.authenticated = True; st.rerun()
else:
    with st.sidebar:
        if st.button("🔒 LOCK"): st.session_state.authenticated = False; st.rerun()
        menu = st.radio("System Modules", ["📺 LIVE VISION", "🔍 SEARCH", "➕ ENROLL USER", "📝 MODIFY PERSONNEL", "🗑️ TERMINATE", "📂 DIRECTORY", "📊 REPORTS"])

    rtc_config = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

    if menu == "📺 LIVE VISION":
        webrtc_streamer(key="vision", video_processor_factory=FaceRecognitionTransformer, media_stream_constraints={"video": True, "audio": False}, rtc_configuration=rtc_config)

    elif menu == "🔍 SEARCH":
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM employees WHERE id=%s", conn, params=(sid,))
            st.dataframe(df); conn.close()

    elif menu == "➕ ENROLL USER":
        st.subheader("Enrollment Pipeline")
        if st.session_state.enroll_step == 1:
            webrtc_streamer(key="enroll_scan", video_processor_factory=EnrollmentTransformer, rtc_configuration=rtc_config)
            if st.button("NEXT"): st.session_state.enroll_step = 2; st.rerun()
        else:
            with st.form("enroll_form"):
                c1, c2 = st.columns(2)
                with c1:
                    fn = st.text_input("First Name"); ln = st.text_input("Last Name"); dept = st.text_input("Dept"); title = st.text_input("Job Title"); nid = st.text_input("National ID"); dob = st.text_input("DOB")
                with c2:
                    hire = st.text_input("Hire Date"); phone = st.text_input("Phone"); e_cont = st.text_input("Emergency Contact"); blood = st.text_input("Blood Type"); branch = st.text_input("Branch"); access = st.number_input("Access Level", 1, 5)
                if st.form_submit_button("COMMIT"):
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("INSERT INTO employees (first_name, last_name, dept_name, job_title, national_id, dob, hire_date, phone, emergency_contact, blood_type, branch, access_level) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (fn, ln, dept, title, nid, dob, hire, phone, e_cont, blood, branch, access))
                    conn.commit(); conn.close(); st.success("Enrolled!"); st.session_state.enroll_step = 1; st.rerun()

    elif menu == "📝 MODIFY PERSONNEL":
        mid = st.number_input("Target ID", min_value=1)
        if st.button("FETCH"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id=%s", (mid,))
            st.session_state['res'] = cur.fetchone(); conn.close()
        if st.session_state['res']:
            with st.form("mod_form"):
                # Updated to include all 12 parameters
                r = st.session_state['res']
                n_fn = st.text_input("First Name", value=r[1]); n_ln = st.text_input("Last Name", value=r[2]); n_dept = st.text_input("Dept", value=r[3])
                n_title = st.text_input("Job Title", value=r[4]); n_nid = st.text_input("Nat ID", value=r[5]); n_dob = st.text_input("DOB", value=r[6])
                n_hire = st.text_input("Hire Date", value=r[7]); n_ph = st.text_input("Phone", value=r[8]); n_em = st.text_input("Emergency Contact", value=r[9])
                n_bl = st.text_input("Blood Type", value=r[10]); n_br = st.text_input("Branch", value=r[11]); n_acc = st.number_input("Access Level", value=r[12])
                if st.form_submit_button("OVERWRITE"):
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s, last_name=%s, dept_name=%s, job_title=%s, national_id=%s, dob=%s, hire_date=%s, phone=%s, emergency_contact=%s, blood_type=%s, branch=%s, access_level=%s WHERE id=%s", 
                                (n_fn, n_ln, n_dept, n_title, n_nid, n_dob, n_hire, n_ph, n_em, n_bl, n_br, n_acc, mid))
                    conn.commit(); conn.close(); st.success("Updated!"); st.session_state['res'] = None; st.rerun()

    elif menu == "📂 DIRECTORY":
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM employees", conn)
        st.dataframe(df); conn.close()

    elif menu == "🗑️ TERMINATE":
        tid = st.number_input("Target ID", min_value=1)
        if st.button("TOGGLE"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("UPDATE employees SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=%s", (tid,))
            conn.commit(); conn.close(); st.success("Toggled!")
