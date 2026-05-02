import asyncio
import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase
import av
import cv2
import os
import pandas as pd
import numpy as np
import base64
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import time
import psycopg2
from supabase import create_client

# --- 1. CONFIG & AUTH SETTINGS ---
st.set_page_config(page_title="NEURAL HR OS 2026", layout="wide", page_icon="🛡️")
supabase = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

def get_db_connection():
    return psycopg2.connect(st.secrets["postgres"]["url"])

def send_security_notification(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'], msg['To'] = "mohamedauoup@gmail.com", "mohamedauoup@gmail.com"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("mohamedauoup@gmail.com", "xjpwurhrozvybini") 
            server.send_message(msg)
    except Exception as e:
        print(f"Email Error: {e}")

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Create table if it doesn't exist
    cur.execute('''CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY, first_name TEXT, last_name TEXT, dept_name TEXT, is_active INTEGER DEFAULT 1)''')
    
    # PATCH: This adds missing columns if your table already existed without them
    columns_to_add = {
        "address": "TEXT",
        "shift_start": "TEXT",
        "phone": "TEXT",
        "salary": "REAL"
    }
    for col_name, col_type in columns_to_add.items():
        try:
            cur.execute(f"ALTER TABLE employees ADD COLUMN {col_name} {col_type}")
        except psycopg2.errors.DuplicateColumn:
            conn.rollback() # Column already exists, ignore
        else:
            conn.commit()

    cur.execute('''CREATE TABLE IF NOT EXISTS attendance (id SERIAL PRIMARY KEY, emp_id INTEGER, name TEXT, date TEXT, clock_in TEXT, clock_out TEXT)''')
    conn.commit(); cur.close(); conn.close()

init_db()

PASS_FILE = "hr_password.txt"
MASTER_KEY = "1234567"
if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("123")

# --- 2. VIDEO BACKGROUND LOGIC ---
@st.cache_data
def get_video_base64(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
    return None

video_base64 = get_video_base64("1.mp4")
if video_base64:
    st.markdown(f"""
        <style>
        #bg-video {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; object-fit: cover; z-index: -1; }}
        .stApp {{ background: transparent !important; }}
        </style>
        <video autoplay loop muted playsinline id="bg-video"><source src="data:video/mp4;base64,{video_base64}" type="video/mp4"></video>
    """, unsafe_allow_html=True)

# --- 3. TRANSFORMERS ---
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

class FaceRecognitionTransformer(VideoProcessorBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.last_email_time = 0

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        conn = get_db_connection(); cur = conn.cursor()
        for (x, y, w, h) in faces:
            cur.execute("SELECT first_name, is_active FROM employees ORDER BY id DESC LIMIT 1")
            res = cur.fetchone()
            if res:
                name, active = res
                color = (0, 255, 0) if active == 1 else (0, 0, 255)
                status = "ACTIVE" if active == 1 else "TERMINATED"
                if active == 0 and (time.time() - self.last_email_time > 60):
                    send_security_notification("ALERT", f"Terminated personnel {name} detected!")
                    self.last_email_time = time.time()
                cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                cv2.putText(img, f"{name} - {status}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        cur.close(); conn.close()
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- 4. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "res" not in st.session_state: st.session_state.res = None

if not st.session_state.authenticated:
    col = st.columns([1, 1.5, 1])[1]
    with col:
        pwd = st.text_input("HR Security Password", type="password")
        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip(): st.session_state.authenticated = True; st.rerun()
else:
    with st.sidebar:
        if st.button("🔒 LOCK CONSOLE"): st.session_state.authenticated = False; st.rerun()
        menu = st.radio("Modules", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL", "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    if menu == "📺 LIVE VISION":
        webrtc_streamer(key="vision", video_processor_factory=FaceRecognitionTransformer)

    elif menu == "➕ ENROLL USER":
        st.subheader("Facial Feature Scanning")
        webrtc_streamer(key="enroll_cam", video_processor_factory=EnrollmentTransformer)
        with st.form("enroll_form"):
            fn = st.text_input("First Name"); ln = st.text_input("Second Name (Last Name)")
            dept = st.text_input("Department"); addr = st.text_input("Address")
            shift = st.text_input("Shift Start"); ph = st.text_input("Phone"); sal = st.number_input("Salary")
            if st.form_submit_button("✨ COMMIT TO DATABASE"):
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO employees (first_name, last_name, dept_name, address, shift_start, phone, salary) VALUES (%s, %s, %s, %s, %s, %s, %s)", (fn, ln, dept, addr, shift, ph, sal))
                conn.commit(); conn.close(); st.success("✅ Enrolled!"); st.balloons()

    elif menu == "📂 STAFF DIRECTORY":
        conn = get_db_connection()
        # Fixed query to match the updated schema
        df = pd.read_sql_query("SELECT id, first_name, last_name, dept_name, phone, address, salary FROM employees WHERE is_active=1", conn)
        conn.close(); st.dataframe(df)

    elif menu == "🔍 SEARCH BY ID":
        sid = st.text_input("ID")
        if st.button("QUERY"):
            conn = get_db_connection(); df = pd.read_sql_query("SELECT * FROM employees WHERE id=%s", conn, params=(sid,)); st.dataframe(df); conn.close()

    elif menu == "📝 MODIFY PERSONNEL":
        mid = st.number_input("ID", min_value=1)
        if st.button("FETCH"):
            conn = get_db_connection(); cur = conn.cursor(); cur.execute("SELECT * FROM employees WHERE id=%s", (mid,)); st.session_state['res'] = cur.fetchone(); conn.close()
        if st.session_state['res']:
            with st.form("mod"):
                n_fn = st.text_input("First Name", value=st.session_state['res'][1])
                n_ph = st.text_input("Phone", value=st.session_state['res'][6] if st.session_state['res'][6] else "")
                if st.form_submit_button("SAVE"):
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s, phone=%s WHERE id=%s", (n_fn, n_ph, mid))
                    conn.commit(); conn.close(); st.success("Updated!"); st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        tid = st.number_input("ID to Terminate", min_value=1)
        if st.button("TERMINATE"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("UPDATE employees SET is_active=0 WHERE id=%s", (tid,))
            conn.commit(); conn.close(); st.warning("Access Revoked")

    elif menu == "📊 DAILY REPORTS":
        conn = get_db_connection(); df = pd.read_sql_query("SELECT * FROM attendance", conn); st.dataframe(df); conn.close()
