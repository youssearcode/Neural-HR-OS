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
    except Exception as e: st.error(f"Email Failed: {e}")

def init_db():
    conn = get_db_connection(); cur = conn.cursor()
    # Expanded schema with new parameters
    cur.execute('''CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY, first_name TEXT, last_name TEXT, dept_name TEXT, 
        address TEXT, shift_start TEXT, phone TEXT, salary REAL, is_active INTEGER DEFAULT 1)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS attendance (id SERIAL PRIMARY KEY, emp_id INTEGER, name TEXT, date TEXT, clock_in TEXT, clock_out TEXT)''')
    conn.commit(); cur.close(); conn.close()

init_db()

PASS_FILE = "hr_password.txt"
MASTER_KEY = "1234567"
if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("123")

# --- 2. VIDEO BACKGROUND FUNCTION ---
@st.cache_data
def get_video_base64(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
    return None

def apply_custom_styles():
    video_base64 = get_video_base64("1.mp4")
    video_html = f'<video autoplay loop muted playsinline id="bg-video"><source src="data:video/mp4;base64,{video_base64}" type="video/mp4"></video>' if video_base64 else ""
    st.markdown(f"""{video_html}
        <style>
        #bg-video {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; object-fit: cover; z-index: -1; }}
        .stApp {{ background: transparent !important; }}
        </style>""", unsafe_allow_html=True)

# --- 3. TRANSFORMERS (Integrated Security Logic) ---
class FaceRecognitionTransformer(VideoProcessorBase):
    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        conn = get_db_connection()
        for (x, y, w, h) in faces:
            cur = conn.cursor()
            cur.execute("SELECT first_name, is_active FROM employees LIMIT 1")
            res = cur.fetchone()
            if res:
                name, active = res
                color = (0, 255, 0) if active == 1 else (0, 0, 255)
                status = "ACTIVE" if active == 1 else "TERMINATED"
                if active == 0: send_security_notification("SECURITY ALERT", f"Terminated person {name} detected!")
                cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                cv2.putText(img, f"{name} - {status}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            cur.close()
        conn.close()
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- 4. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "res" not in st.session_state: st.session_state.res = None
apply_custom_styles()

if not st.session_state.authenticated:
    col = st.columns([1, 1.5, 1])[1]
    with col:
        pwd = st.text_input("HR Security Password", type="password")
        with st.expander("Forgot Password?"):
            mk = st.text_input("Enter Master Key", type="password"); npwd = st.text_input("Enter New Password", type="password")
            if st.button("RESET PASSWORD"):
                if mk == MASTER_KEY:
                    with open(PASS_FILE, "w") as f: f.write(npwd); st.success("Password Updated!"); st.rerun()
                else: st.error("Invalid Master Key")
        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip(): st.session_state.authenticated = True; st.rerun()
else:
    with st.sidebar:
        if st.button("🔒 LOCK CONSOLE"): st.session_state.authenticated = False; st.rerun()
        menu = st.radio("System Modules", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL", "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    if menu == "📺 LIVE VISION":
        webrtc_streamer(key="vision", video_processor_factory=FaceRecognitionTransformer, async_processing=True)
    elif menu == "🔍 SEARCH BY ID":
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            conn = get_db_connection(); df = pd.read_sql_query("SELECT * FROM employees WHERE id=%s", conn, params=(sid,)); st.dataframe(df); conn.close()
    elif menu == "➕ ENROLL USER":
        with st.form("enroll_form"):
            fn = st.text_input("First Name"); ln = st.text_input("Last Name"); dept = st.text_input("Department")
            addr = st.text_input("Address"); shift = st.text_input("Shift Start"); ph = st.text_input("Phone"); sal = st.number_input("Salary")
            if st.form_submit_button("✨ COMMIT TO DATABASE"):
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO employees (first_name, last_name, dept_name, address, shift_start, phone, salary) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (fn, ln, dept, addr, shift, ph, sal))
                conn.commit(); cur.close(); conn.close(); st.success("✅ Enrolled!"); st.balloons()
    elif menu == "📝 MODIFY PERSONNEL":
        mid = st.number_input("Target ID", min_value=1)
        if st.button("FETCH PROFILE"):
            conn = get_db_connection(); cur = conn.cursor(); cur.execute("SELECT * FROM employees WHERE id=%s", (mid,)); st.session_state['res'] = cur.fetchone(); conn.close()
        if 'res' in st.session_state and st.session_state['res']:
            with st.form("mod_form"):
                n_fn = st.text_input("First Name", value=st.session_state['res'][1])
                n_addr = st.text_input("Address", value=st.session_state['res'][4])
                if st.form_submit_button("💾 OVERWRITE"):
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s, address=%s WHERE id=%s", (n_fn, n_addr, mid))
                    conn.commit(); cur.close(); conn.close(); st.success("✅ Updated!"); st.rerun()
    elif menu == "🗑️ TERMINATE ACCESS":
        tid = st.number_input("Target ID", min_value=1)
        if st.button("TERMINATE"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("UPDATE employees SET is_active=0 WHERE id=%s", (tid,))
            conn.commit(); cur.close(); conn.close(); st.warning("⚠️ Access Revoked")
    elif menu == "📂 STAFF DIRECTORY":
        conn = get_db_connection(); df = pd.read_sql_query("SELECT id, first_name, last_name, dept_name FROM employees WHERE is_active=1", conn); conn.close(); st.dataframe(df)
    elif menu == "📊 DAILY REPORTS":
        if st.button("🚨 DELETE ALL DATA"):
            conn = get_db_connection(); cur = conn.cursor(); cur.execute("DELETE FROM employees"); cur.execute("DELETE FROM attendance"); conn.commit(); conn.close(); st.error("Data Wiped")
        conn = get_db_connection(); df = pd.read_sql_query("SELECT * FROM attendance", conn); st.dataframe(df); conn.close()
