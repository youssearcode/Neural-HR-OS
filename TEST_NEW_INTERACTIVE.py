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

# CLOUD FIX: Required for Streamlit Cloud to connect to your local webcam
RTC_CONFIGURATION = {
    "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
}

def get_db_connection():
    return psycopg2.connect(st.secrets["postgres"]["url"])

def send_security_notification(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'], msg['To'] = "mohamedauoup@gmail.com", "mohamedauoup@gmail.com"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            # Note: Ensure you are using a 16-character Google App Password here
            server.login("mohamedauoup@gmail.com", "xjpwurhrozvybini") 
            server.send_message(msg)
    except Exception as e:
        print(f"Email Error: {e}")

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Ensure table exists
    cur.execute('''CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY, first_name TEXT, last_name TEXT, dept_name TEXT, is_active INTEGER DEFAULT 1)''')
    
    # DATABASE PATCH: Automatically adds missing columns to prevent "UndefinedColumn" errors
    patch_columns = {
        "address": "TEXT",
        "shift_start": "TEXT",
        "phone": "TEXT",
        "salary": "REAL"
    }
    for col_name, col_type in patch_columns.items():
        try:
            cur.execute(f"ALTER TABLE employees ADD COLUMN {col_name} {col_type}")
            conn.commit()
        except Exception:
            conn.rollback() # Column likely already exists

    cur.execute('''CREATE TABLE IF NOT EXISTS attendance (id SERIAL PRIMARY KEY, emp_id INTEGER, name TEXT, date TEXT, clock_in TEXT, clock_out TEXT)''')
    conn.commit(); cur.close(); conn.close()

init_db()

PASS_FILE = "hr_password.txt"
MASTER_KEY = "1234567"
if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("123")

# --- 2. VIDEO BACKGROUND ---
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
            cur.execute("SELECT id, first_name, last_name, is_active FROM employees ORDER BY id DESC LIMIT 1")
            res = cur.fetchone()
            if res:
                uid, fname, lname, active = res
                full_name = f"{fname} {lname}"
                color = (0, 255, 0) if active == 1 else (0, 0, 255)
                status = "ACTIVE" if active == 1 else "TERMINATED"
                
                if active == 0 and (time.time() - self.last_email_time > 60):
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    alert_msg = f"ALERT: Terminated Person Detected!\n\nName: {full_name}\nID: {uid}\nTime: {now}"
                    send_security_notification("SECURITY BREACH DETECTED", alert_msg)
                    self.last_email_time = time.time()
                
                cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                cv2.putText(img, f"{full_name} - {status}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        cur.close(); conn.close()
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- 4. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "res" not in st.session_state: st.session_state.res = None

if not st.session_state.authenticated:
    col = st.columns([1, 1.5, 1])[1]
    with col:
        st.title("🛡️ HR ACCESS PANEL")
        pwd = st.text_input("Console Password", type="password")
        
        with st.expander("🔑 Reset System Access"):
            f_mk = st.text_input("Master Security Key", type="password")
            f_np = st.text_input("New Access Password", type="password")
            f_cp = st.text_input("Confirm New Password", type="password")
            
            if st.button("RESET SYSTEM PASSWORD"):
                if not f_mk or not f_np or not f_cp:
                    st.error("All fields (Master Key, New Pass, Confirm Pass) must be entered!")
                elif f_np != f_cp:
                    st.error("New Passwords do not match!")
                elif f_mk != MASTER_KEY:
                    st.error("Invalid Master Security Key!")
                else:
                    with open(PASS_FILE, "w") as f: f.write(f_np)
                    send_security_notification("System Password Changed", f"The HR Console password was reset successfully at {datetime.now()}.")
                    st.success("System Password Updated!"); time.sleep(1); st.rerun()

        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip(): st.session_state.authenticated = True; st.rerun()
else:
    with st.sidebar:
        st.header("NEURAL HR OS")
        if st.button("🔒 LOCK CONSOLE"): st.session_state.authenticated = False; st.rerun()
        menu = st.radio("Management", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL", "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    if menu == "📺 LIVE VISION":
        # CLOUD FIX: Applied rtc_configuration
        webrtc_streamer(key="vision", video_processor_factory=FaceRecognitionTransformer, rtc_configuration=RTC_CONFIGURATION)

    elif menu == "➕ ENROLL USER":
        st.subheader("Facial Bio-Scanning")
        # CLOUD FIX: Applied rtc_configuration
        webrtc_streamer(key="enroll_cam", video_processor_factory=EnrollmentTransformer, rtc_configuration=RTC_CONFIGURATION)
        with st.form("enroll_form"):
            col1, col2 = st.columns(2)
            with col1:
                fn = st.text_input("First Name"); ln = st.text_input("Second Name (Last Name)")
                dept = st.text_input("Department")
            with col2:
                addr = st.text_input("Address"); ph = st.text_input("Phone Number")
                shift = st.text_input("Shift Start (e.g. 08:00 AM)")
            sal = st.number_input("Salary ($)", min_value=0.0)
            
            if st.form_submit_button("✨ COMMIT ENROLLMENT"):
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO employees (first_name, last_name, dept_name, address, shift_start, phone, salary) VALUES (%s, %s, %s, %s, %s, %s, %s)", (fn, ln, dept, addr, shift, ph, sal))
                conn.commit(); conn.close()
                st.success(f"✅ {fn} {ln} Enrolled Successfully!"); st.balloons()

    elif menu == "📂 STAFF DIRECTORY":
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, first_name, last_name, dept_name, phone, address, salary, is_active FROM employees WHERE is_active=1", conn)
        conn.close(); st.dataframe(df, use_container_width=True)

    elif menu == "🔍 SEARCH BY ID":
        sid = st.text_input("Enter Employee ID")
        if st.button("FETCH DATA"):
            conn = get_db_connection(); df = pd.read_sql_query("SELECT * FROM employees WHERE id=%s", conn, params=(sid,)); st.dataframe(df); conn.close()

    elif menu == "📝 MODIFY PERSONNEL":
        mid = st.number_input("Employee ID to Edit", min_value=1)
        if st.button("LOAD PROFILE"):
            conn = get_db_connection(); cur = conn.cursor(); cur.execute("SELECT * FROM employees WHERE id=%s", (mid,)); st.session_state['res'] = cur.fetchone(); conn.close()
        if st.session_state['res']:
            with st.form("mod"):
                n_fn = st.text_input("First Name", value=st.session_state['res'][1])
                n_ln = st.text_input("Second Name", value=st.session_state['res'][2])
                n_ph = st.text_input("Phone", value=st.session_state['res'][6] if st.session_state['res'][6] else "")
                n_sal = st.number_input("Salary", value=float(st.session_state['res'][7]) if st.session_state['res'][7] else 0.0)
                if st.form_submit_button("UPDATE RECORD"):
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s, last_name=%s, phone=%s, salary=%s WHERE id=%s", (n_fn, n_ln, n_ph, n_sal, mid))
                    conn.commit(); conn.close(); st.success("Database Updated!"); st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        tid = st.number_input("Employee ID to Revoke", min_value=1)
        if st.button("REVOKE ACCESS"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("UPDATE employees SET is_active=0 WHERE id=%s", (tid,))
            conn.commit(); conn.close(); st.warning(f"Employee {tid} access status set to TERMINATED.")

    elif menu == "📊 DAILY REPORTS":
        conn = get_db_connection(); df = pd.read_sql_query("SELECT * FROM attendance", conn); st.dataframe(df, use_container_width=True); conn.close()
