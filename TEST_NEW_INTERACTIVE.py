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
from datetime import datetime
import time
import psycopg2
from supabase import create_client

# --- 0. CONSTANTS & UTILS (Missing in original snippet) ---
PASS_FILE = "secret_password.txt"
MASTER_KEY = "ADMIN123"
if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("admin123")

def apply_custom_styles():
    st.markdown("""<style> .main { background-color: #0e1117; } </style>""", unsafe_allow_html=True)

# --- 1. CONFIG & AUTH SETTINGS ---
st.set_page_config(page_title="NEURAL HR OS 2026", layout="wide", page_icon="🛡️")

# Initialize Supabase (Ensure these exist in your secrets)
try:
    supabase = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
except:
    st.warning("Supabase credentials missing. DB functions might fail.")

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
        print(f"Email Failed: {e}")

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
    except Exception as e:
        st.error(f"DB Init Error: {e}")

init_db()

# --- 2. CONSOLIDATED TRANSFORMERS ---
class FaceRecognitionTransformer(VideoProcessorBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)

        # To prevent the 'NoneType' asyncio error, we handle DB connections carefully inside the thread
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
                    if active == 0: 
                        send_security_notification("SECURITY ALERT", f"Terminated person {name} detected!")
                    
                    cv2.rectangle(img, (x, y), (x + w, h + y), color, 2)
                    cv2.putText(img, f"{name} - {status}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            cur.close()
            conn.close()
        except:
            # Fallback if DB is busy or loop is closing
            for (x, y, w, h) in faces:
                cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 0), 2)
                cv2.putText(img, "SCANNING...", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

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
            cv2.putText(img, "SCANNING...", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- 3. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "res" not in st.session_state: st.session_state.res = None

apply_custom_styles()

if not st.session_state.authenticated:
    col = st.columns([1, 1.5, 1])[1]
    with col:
        st.title("NEURAL HR OS")
        pwd = st.text_input("HR Security Password", type="password")
        
        with st.expander("Forgot Password?"):
            mk = st.text_input("Enter Master Key", type="password")
            npwd = st.text_input("Enter New Password", type="password")
            if st.button("RESET PASSWORD"):
                if mk == MASTER_KEY:
                    with open(PASS_FILE, "w") as f: f.write(npwd)
                    st.success("Password Updated!"); time.sleep(1); st.rerun()
                else: st.error("Invalid Master Key")

        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip():
                    st.session_state.authenticated = True
                    send_security_notification("Access Alert", "System accessed at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    st.rerun()
else:
    with st.sidebar:
        if st.button("🔒 LOCK CONSOLE"): st.session_state.authenticated = False; st.rerun()
        menu = st.radio("System Modules", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL", "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    if menu == "📺 LIVE VISION":
        st.subheader("Real-time Neural Monitoring")
        webrtc_streamer(
            key="vision", 
            video_processor_factory=FaceRecognitionTransformer,
            async_processing=True, # Set to False if the 'NoneType' error persists
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
        )

    elif menu == "🔍 SEARCH BY ID":
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT id, first_name, last_name, dept_name, is_active FROM employees WHERE id=%s", conn, params=(sid,))
            st.dataframe(df)
            conn.close()

    elif menu == "➕ ENROLL USER":
        # Integrating the scanning camera inside enrollment
        st.write("Position face in camera for scanning:")
        webrtc_streamer(key="enroll_cam", video_processor_factory=EnrollmentTransformer)
        
        with st.form("enroll_form"):
            fn = st.text_input("First Name")
            ln = st.text_input("Last Name")
            dept = st.text_input("Department")
            if st.form_submit_button("✨ COMMIT TO DATABASE"):
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO employees (first_name, last_name, dept_name) VALUES (%s, %s, %s)", (fn, ln, dept))
                conn.commit()
                cur.close()
                conn.close()
                st.success("✅ Employee enrolled successfully!")
                st.balloons()

    elif menu == "📝 MODIFY PERSONNEL":
        mid = st.number_input("Target ID", min_value=1)
        if st.button("FETCH PROFILE"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id=%s", (mid,))
            st.session_state['res'] = cur.fetchone()
            conn.close()
        
        if st.session_state['res']:
            with st.form("mod_form"):
                n_fn = st.text_input("First Name", value=st.session_state['res'][1])
                if st.form_submit_button("💾 OVERWRITE"):
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s WHERE id=%s", (n_fn, mid))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success("✅ Profile updated!")
                    st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        tid = st.number_input("Target ID", min_value=1)
        if st.button("TERMINATE"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE employees SET is_active=0 WHERE id=%s", (tid,))
            conn.commit()
            cur.close()
            conn.close()
            st.warning("⚠️ Access Revoked")

    elif menu == "📂 STAFF DIRECTORY":
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, first_name, last_name, dept_name, is_active FROM employees", conn)
        conn.close()
        st.dataframe(df)

    elif menu == "📊 DAILY REPORTS":
        if st.button("🚨 DELETE ALL DATA"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM employees")
            cur.execute("DELETE FROM attendance")
            conn.commit()
            conn.close()
            st.error("Data Wiped")
        
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM attendance", conn)
        st.dataframe(df)
        conn.close()
