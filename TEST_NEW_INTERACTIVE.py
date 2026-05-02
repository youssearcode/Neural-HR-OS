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


def upload_to_supabase(image_bytes, file_name):
    try:
        supabase.storage.from_("employee-photos").upload(path=file_name, file=image_bytes,
                                                         file_options={"content-type": "image/jpeg"})
        return supabase.storage.from_("employee-photos").get_public_url(file_name)
    except:
        return None


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Updated schema to include: address, shift_start, phone, salary
    cur.execute(
        '''CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY, 
            first_name TEXT, 
            last_name TEXT, 
            dept_name TEXT, 
            address TEXT,
            shift_start TEXT,
            phone TEXT,
            salary REAL,
            is_active INTEGER DEFAULT 1)''')
    cur.execute(
        '''CREATE TABLE IF NOT EXISTS attendance (id SERIAL PRIMARY KEY, emp_id INTEGER, name TEXT, date TEXT, clock_in TEXT, clock_out TEXT)''')
    conn.commit()
    cur.close()
    conn.close()


init_db()

PASS_FILE = "hr_password.txt"
MASTER_KEY = "1234567"
if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("123")

# --- 2. EMAIL NOTIFICATION FUNCTION ---
def send_security_notification(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'], msg['To'] = "mohamedauoup@gmail.com", "mohamedauoup@gmail.com"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            # Use your 16-character App Password here
            server.login("mohamedauoup@gmail.com", "xjpwurhrozvybini") 
            server.send_message(msg)
    except Exception as e: 
        # Using print here as st.error doesn't always render from inside the WebRTC thread
        print(f"Email Failed: {e}")


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
            cv2.putText(img, "SCANNING...", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

class FaceRecognitionTransformer(VideoProcessorBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.last_alert_time = 0 # To prevent spamming emails

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        
        # Note: In a production environment, actual face recognition (DeepFace/FaceNet) 
        # would be used here to get the 'target_id'. For this logic, we query the DB status.
        conn = get_db_connection()
        cur = conn.cursor()

        for (x, y, w, h) in faces:
            # Logic: Simulating recognition by looking up the most recent entry or a match
            cur.execute("SELECT first_name, last_name, is_active FROM employees ORDER BY id DESC LIMIT 1")
            user_data = cur.fetchone()

            if user_data:
                first_name, last_name, is_active = user_data
                full_name = f"{first_name} {last_name}"

                if is_active == 1:
                    # GREEN BOX for Active
                    color = (0, 255, 0)
                    label = f"{full_name} (ACTIVE)"
                else:
                    # RED BOX for Terminated
                    color = (0, 0, 255)
                    label = "WARNING: TERMINATED"
                    
                    # Send Security Email (once every 60 seconds to avoid spam)
                    current_time = time.time()
                    if current_time - self.last_alert_time > 60:
                        send_security_notification(
                            "SECURITY ALERT: Terminated Personnel Detected",
                            f"Terminated employee {full_name} was detected by LIVE VISION at {datetime.now()}."
                        )
                        self.last_alert_time = current_time

                cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            else:
                # Unknown detections
                cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 0), 2)
                cv2.putText(img, "UNKNOWN", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
        
        cur.close()
        conn.close()
        return av.VideoFrame.from_ndarray(img, format="bgr24")


# --- 4. MAIN APP LOGIC ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "res" not in st.session_state: st.session_state.res = None

if not st.session_state.authenticated:
    col = st.columns([1, 1.5, 1])[1]
    with col:
        pwd = st.text_input("HR Security Password", type="password")
        with st.expander("Forgot Password?"):
            mk = st.text_input("Enter Master Key", type="password")
            npwd = st.text_input("Enter New Password", type="password")
            if st.button("RESET PASSWORD"):
                if mk == MASTER_KEY:
                    with open(PASS_FILE, "w") as f:
                        f.write(npwd)
                    st.success("Password Updated!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid Master Key")

        if st.button("AUTHORIZE ACCESS"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip(): 
                    st.session_state.authenticated = True
                    st.rerun()
else:
    with st.sidebar:
        if st.button("🔒 LOCK CONSOLE"): 
            st.session_state.authenticated = False
            st.rerun()
        menu = st.radio("System Modules", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL",
                                           "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    if menu == "📺 LIVE VISION":
        st.subheader("Real-Time Personnel Monitoring")
        webrtc_streamer(key="vision", video_processor_factory=FaceRecognitionTransformer, async_processing=True)

    elif menu == "🔍 SEARCH BY ID":
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM employees WHERE id=%s", conn, params=(sid,))
            if not df.empty:
                st.dataframe(df)
            else:
                st.warning("No personnel found with this ID.")
            conn.close()

    elif menu == "➕ ENROLL USER":
        with st.form("enroll_form"):
            col1, col2 = st.columns(2)
            with col1:
                fn = st.text_input("First Name")
                ln = st.text_input("Second Name (Last Name)")
                dept = st.text_input("Department")
            with col2:
                addr = st.text_input("Address")
                shift = st.text_input("Shift Start (e.g., 09:00 AM)")
                ph = st.text_input("Phone Number")
            
            sal = st.number_input("Salary", min_value=0.0)
            
            if st.form_submit_button("✨ COMMIT TO DATABASE"):
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""INSERT INTO employees (first_name, last_name, dept_name, address, shift_start, phone, salary) 
                               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                            (fn, ln, dept, addr, shift, ph, sal))
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
                st.info(f"Modifying Profile for ID: {mid}")
                m_fn = st.text_input("First Name", value=st.session_state['res'][1])
                m_ln = st.text_input("Second Name", value=st.session_state['res'][2])
                m_dept = st.text_input("Department", value=st.session_state['res'][3])
                m_addr = st.text_input("Address", value=st.session_state['res'][4] if st.session_state['res'][4] else "")
                m_shift = st.text_input("Shift Start", value=st.session_state['res'][5] if st.session_state['res'][5] else "")
                m_phone = st.text_input("Phone", value=st.session_state['res'][6] if st.session_state['res'][6] else "")
                m_sal = st.number_input("Salary", value=float(st.session_state['res'][7]) if st.session_state['res'][7] else 0.0)

                if st.form_submit_button("💾 OVERWRITE"):
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("""UPDATE employees SET 
                                   first_name=%s, last_name=%s, dept_name=%s, 
                                   address=%s, shift_start=%s, phone=%s, salary=%s 
                                   WHERE id=%s""", 
                                (m_fn, m_ln, m_dept, m_addr, m_shift, m_phone, m_sal, mid))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success("✅ Profile updated!")
                    st.session_state['res'] = None
                    time.sleep(1)
                    st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        tid = st.number_input("Target ID to Terminate", min_value=1)
        if st.button("TERMINATE"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE employees SET is_active=0 WHERE id=%s", (tid,))
            conn.commit()
            cur.close()
            conn.close()
            st.warning(f"⚠️ Access Revoked for ID {tid}. Live Vision will now flag this person.")

    elif menu == "📂 STAFF DIRECTORY":
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, first_name, last_name, dept_name, phone, is_active FROM employees WHERE is_active=1", conn)
        conn.close()
        st.dataframe(df, use_container_width=True)

    elif menu == "📊 DAILY REPORTS":
        if st.button("🚨 DELETE ALL DATA"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM employees")
            cur.execute("DELETE FROM attendance")
            conn.commit()
            conn.close()
            st.error("Data Wiped")
            st.rerun()
            
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM attendance", conn)
        st.dataframe(df, use_container_width=True)
        conn.close()
