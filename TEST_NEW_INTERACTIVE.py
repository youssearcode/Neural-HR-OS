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

# --- FIX: Asyncio Loop Initialization ---
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# --- 1. CONFIG & AUTH SETTINGS ---
st.set_page_config(page_title="NEURAL HR OS 2026", layout="wide", page_icon="🛡️")

# Initialize Supabase Client
supabase = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

# --- 2. DATABASE & MIGRATION ---
def get_db_connection():
    return psycopg2.connect(st.secrets["postgres"]["url"])

def upload_to_supabase(image_bytes, file_name):
    try:
        supabase.storage.from_("employee-photos").upload(
            path=file_name, file=image_bytes, file_options={"content-type": "image/jpeg"}
        )
        return supabase.storage.from_("employee-photos").get_public_url(file_name)
    except Exception as e:
        st.error(f"Upload Failed: {e}")
        return None

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY, first_name TEXT, last_name TEXT, dept_name TEXT, 
        address TEXT, email TEXT, contact TEXT, emergency_contact TEXT, 
        compensation TEXT, performance TEXT, folder_name TEXT, 
        shift_start TEXT DEFAULT '09:00', grace_period INTEGER DEFAULT 15, 
        current_status TEXT DEFAULT 'Office', is_active INTEGER DEFAULT 1, photo_url TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id SERIAL PRIMARY KEY, emp_id INTEGER, name TEXT, date TEXT, 
        clock_in TEXT, clock_out TEXT, late_minutes INTEGER, penalty TEXT, status TEXT)''')
    conn.commit(); cur.close(); conn.close()

init_db()

# --- 3. SYSTEM GLOBALS ---
EMAIL_USER = "mohamedauoup@gmail.com"
EMAIL_PASS = "xjpwurhrozvybini"
HR_RECIPIENT = "mohamedauoup@gmail.com"
PASS_FILE = "hr_password.txt"

if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("123")

# --- 4. CACHED VIDEO & STYLES ---
@st.cache_data
def get_video_base64(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return None

def apply_custom_styles():
    video_path = "1.mp4"
    video_base64 = get_video_base64(video_path)
    video_html = f'<video autoplay loop muted playsinline id="bg-video"><source src="data:video/mp4;base64,{video_base64}" type="video/mp4"></video>' if video_base64 else ""
    st.markdown(f"""{video_html}
        <style>
        #bg-video {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; object-fit: cover; z-index: -1; }}
        .stApp {{ background: transparent !important; }}
        [data-testid="stSidebar"] {{ background-color: rgba(0, 0, 0, 0.4) !important; backdrop-filter: blur(15px); }}
        div[data-testid="stForm"], .stDataFrame, .main-card {{ background-color: rgba(0, 0, 0, 0.3) !important; border-radius: 15px; padding: 25px; backdrop-filter: blur(12px); border: 1px solid rgba(0, 210, 255, 0.2); }}
        h1, h2, h3, p, label {{ color: #ffffff !important; }}
        .stButton>button {{ background-color: rgba(0, 210, 255, 0.3) !important; border: 1px solid #00d2ff !important; color: white !important; }}
        </style>""", unsafe_allow_html=True)

def send_security_notification(subject, body):
    try:
        msg = MIMEText(body); msg['Subject'] = subject
        msg['From'], msg['To'] = EMAIL_USER, HR_RECIPIENT
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS); server.send_message(msg)
    except Exception as e: print(f"Email Failed: {e}")

# --- 5. TRANSFORMERS ---
class FaceRecognitionTransformer(VideoProcessorBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        for (x, y, w, h) in faces: cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- 6. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    apply_custom_styles()
    col = st.columns([1, 1.5, 1])[1]
    with col:
        pwd = st.text_input("HR Security Password", type="password")
        # Added Forgot Password Logic
        if st.button("Forgot Password?"):
            with open(PASS_FILE, "r") as f:
                send_security_notification("HR OS Password Recovery", f"Current Password: {f.read().strip()}")
                st.info("Check your email!")
        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip(): st.session_state.authenticated = True; st.rerun()
else:
    apply_custom_styles()
    with st.sidebar:
        if st.button("🔒 LOCK CONSOLE"): st.session_state.authenticated = False; st.rerun()
        menu = st.radio("System Modules", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL", "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    if menu == "📺 LIVE VISION":
        webrtc_streamer(key="vision", video_processor_factory=FaceRecognitionTransformer, async_processing=True)

    elif menu == "🔍 SEARCH BY ID":
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM employees WHERE id=%s", conn, params=(sid,))
            st.dataframe(df); conn.close()

    elif menu == "➕ ENROLL USER":
        with st.form("enroll_form"):
            fn = st.text_input("First Name")
            photo = st.camera_input("Capture Biometric ID")
            if st.form_submit_button("✨ COMMIT TO DATABASE"):
                cloud_url = upload_to_supabase(photo.getvalue(), f"{fn}_{int(time.time())}.jpg") if photo else None
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO employees (first_name, photo_url, is_active) VALUES (%s, %s, 1)", (fn, cloud_url))
                conn.commit(); cur.close(); conn.close(); st.success("✅ Enrollment Complete"); st.balloons()

    elif menu == "📝 MODIFY PERSONNEL":
        mid = st.number_input("Target ID", min_value=1)
        if st.button("FETCH PROFILE"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id=%s", (mid,))
            res = cur.fetchone()
            if res: st.session_state['mod_data'] = {"fn": res[1]}
            conn.close()
        if 'mod_data' in st.session_state:
            with st.form("mod_form"):
                n_fn = st.text_input("First Name", value=st.session_state['mod_data']['fn'])
                if st.form_submit_button("💾 OVERWRITE"):
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s WHERE id=%s", (n_fn, mid))
                    conn.commit(); cur.close(); conn.close()
                    st.success("Synchronized!"); st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        tid = st.number_input("Target ID", min_value=1)
        if st.button("TERMINATE"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE employees SET is_active=0 WHERE id=%s", (tid,))
            conn.commit(); cur.close(); conn.close()
            st.warning("Access Revoked")

    elif menu == "📂 STAFF DIRECTORY":
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, first_name, photo_url FROM employees WHERE is_active=1", conn)
        conn.close()
        st.subheader("Current Staff Profiles")
        for index, row in df.iterrows():
            col1, col2 = st.columns([1, 4])
            with col1:
                if row['photo_url']: st.image(row['photo_url'], width=100)
                else: st.write("No Photo")
            with col2:
                st.write(f"**ID:** {row['id']} | **Name:** {row['first_name']}")

    elif menu == "📊 DAILY REPORTS":
        with st.expander("⚠️ DANGER ZONE"):
            if st.button("🚨 DELETE ALL DATA"):
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("DELETE FROM employees"); cur.execute("DELETE FROM attendance")
                conn.commit(); cur.close(); conn.close()
                st.rerun()
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM attendance", conn)
        st.dataframe(df); conn.close()
