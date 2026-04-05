import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import av
import cv2
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import numpy as np
import base64
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import time
import io

# --- 1. CONFIG & AUTH SETTINGS ---
st.set_page_config(page_title="NEURAL HR OS 2026", layout="wide", page_icon="🛡️")

# --- 2. CLOUD DATABASE (SECURE ACCESS) ---
DB_CONFIG = {
    "dbname": st.secrets["database"]["dbname"],
    "user": st.secrets["database"]["user"],
    "password": st.secrets["database"]["password"],
    "host": st.secrets["database"]["host"],
    "port": st.secrets["database"]["port"]
}

def get_db_connection(cursor_factory=None):
    if cursor_factory:
        return psycopg2.connect(**DB_CONFIG, connect_timeout=10, cursor_factory=cursor_factory)
    return psycopg2.connect(**DB_CONFIG, connect_timeout=10)

def init_cloud_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS employees
                    (id SERIAL PRIMARY KEY,
                     first_name TEXT, last_name TEXT, dept_name TEXT,
                     address TEXT, email TEXT, contact TEXT,
                     emergency_contact TEXT, compensation TEXT,
                     performance TEXT, folder_name TEXT,
                     shift_start TEXT DEFAULT '09:00',
                     grace_period INTEGER DEFAULT 15,
                     current_status TEXT DEFAULT 'Office',
                     is_active INTEGER DEFAULT 1)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS attendance
                    (id SERIAL PRIMARY KEY,
                     emp_id INTEGER, name TEXT, date TEXT,
                     clock_in TEXT, clock_out TEXT,
                     late_minutes INTEGER, penalty TEXT,
                     status TEXT)''')
    conn.commit()
    cur.close()
    conn.close()

if 'db_initialized' not in st.session_state:
    init_cloud_db()
    st.session_state.db_initialized = True

# --- 3. SYSTEM GLOBALS ---
EMAIL_USER = "mohamedauoup@gmail.com"
EMAIL_PASS = "xjpwurhrozvybini"
HR_RECIPIENT = "mohamedauoup@gmail.com"
PASS_FILE = "hr_password.txt"
MASTER_KEY = "ADMIN_GATE_2026"  # The Master Key to bypass password reset

if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("123")

# --- 4. UTILITIES ---
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
    st.markdown(f"""{video_html}<style>
        #bg-video {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; object-fit: cover; z-index: -1; }}
        .stApp {{ background: transparent !important; }}
        [data-testid="stHeader"] {{ background: transparent !important; }}
        [data-testid="stSidebar"] {{ background-color: rgba(0, 0, 0, 0.4) !important; backdrop-filter: blur(15px); }}
        div[data-testid="stForm"], .stDataFrame, .main-card {{
            background-color: rgba(0, 0, 0, 0.3) !important; border-radius: 15px; padding: 25px; backdrop-filter: blur(12px);
            border: 1px solid rgba(0, 210, 255, 0.2); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6); margin-bottom: 20px;
        }}
        h1, h2, h3, p, label, .stMarkdown {{ color: #ffffff !important; text-shadow: 1px 1px 3px rgba(0,0,0,0.8); }}
        .stButton>button {{ background-color: rgba(0, 210, 255, 0.3) !important; border: 1px solid #00d2ff !important; color: white !important; border-radius: 10px; }}
        </style>""", unsafe_allow_html=True)

def send_security_alert(subject, body):
    try:
        msg = MIMEText(f"NEURAL HR OS 2026 - SECURITY LOG\nTimestamp: {datetime.now()}\n\n{body}")
        msg['Subject'] = f"🛡️ SYSTEM ALERT: {subject}"
        msg['From'], msg['To'] = EMAIL_USER, HR_RECIPIENT
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except: return False

# --- 5. TRANSFORMERS (OPTIMIZED FOR HIGH SPEED) ---
class EnrollmentTransformer(VideoTransformerBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
            cv2.putText(img, "NEW USER SCANNING...", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        return img

class FaceRecognitionTransformer(VideoTransformerBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.frame_idx = 0
        self.last_db_check = 0

    def mark_attendance(self, emp_id, name, shift_start, grace):
        now = datetime.now()
        today, current_time = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM attendance WHERE emp_id=%s AND date=%s", (emp_id, today))
        exists = cur.fetchone()
        if not exists:
            try:
                s_dt, c_dt = datetime.strptime(shift_start, '%H:%M'), datetime.strptime(current_time, '%H:%M')
                late = max(0, int((c_dt - s_dt).total_seconds() / 60) - grace)
                penalty = f"{late}m Late" if late > 0 else "On Time"
            except: late, penalty = 0, "N/A"
            cur.execute("INSERT INTO attendance (emp_id, name, date, clock_in, late_minutes, penalty, status) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp_id, name, today, current_time, late, penalty, "Office"))
            conn.commit()
        else:
            cur.execute("UPDATE attendance SET clock_out=%s WHERE emp_id=%s AND date=%s", (current_time, emp_id, today))
            conn.commit()
        cur.close(); conn.close()

    def transform(self, frame):
        self.frame_idx += 1
        img = frame.to_ndarray(format="bgr24")
        if self.frame_idx % 4 != 0: return img

        scale = 0.3
        small_img = cv2.resize(img, (0, 0), fx=scale, fy=scale)
        gray = cv2.cvtColor(small_img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.2, 4)
        
        if time.time() - self.last_db_check > 2:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT id, first_name, is_active, shift_start, grace_period FROM employees")
            self.cached_users = cur.fetchall()
            cur.close(); conn.close()
            self.last_db_check = time.time()

        for (x, y, w, h) in faces:
            ix, iy, iw, ih = int(x/scale), int(y/scale), int(w/scale), int(h/scale)
            color, label = (0, 255, 255), "IDENTIFYING..."
            
            if hasattr(self, 'cached_users'):
                for eid, fname, active, shift, grace in self.cached_users:
                    if active == 0: color, label = (0, 0, 255), f"⚠️ BANNED: {fname}"
                    else:
                        color, label = (0, 255, 0), f"VERIFIED: {fname}"
                        self.mark_attendance(eid, fname, shift, grace)
            
            cv2.rectangle(img, (ix, iy), (ix + iw, iy + ih), color, 2)
            cv2.putText(img, label, (ix, iy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        return img

# --- 6. MAIN APP ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    apply_custom_styles()
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown('<div class="main-card" style="margin-top: 15%;">', unsafe_allow_html=True)
        st.title("🛡️ NEURAL GATEWAY")
        
        # Reset Workflow with Master Key
        if st.session_state.get("forget_pwd"):
            st.subheader("🔑 Master Override")
            mk_input = st.text_input("Enter Master Key for access", type="password")
            
            if "mk_verified" not in st.session_state:
                if st.button("VERIFY MASTER KEY", use_container_width=True):
                    if mk_input == MASTER_KEY:
                        st.session_state.mk_verified = True
                        st.rerun()
                    else:
                        st.error("Invalid Master Key.")
            
            if st.session_state.get("mk_verified"):
                new_pass = st.text_input("Define New System Password", type="password")
                conf_pass = st.text_input("Confirm New Password", type="password")
                if st.button("REWRITE CREDENTIALS", use_container_width=True, type="primary"):
                    if new_pass and new_pass == conf_pass:
                        with open(PASS_FILE, "w") as f: f.write(new_pass)
                        send_security_alert("PASSWORD OVERRIDE", "System password was changed using the Master Key.")
                        st.success("Access Restored.")
                        st.session_state.forget_pwd = False
                        st.session_state.mk_verified = False
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Passwords do not match.")
            
            if st.button("Cancel", use_container_width=True):
                st.session_state.forget_pwd = False
                st.session_state.mk_verified = False
                st.rerun()

        else:
            pwd = st.text_input("HR Security Password", type="password")
            c1, c2 = st.columns(2)
            if c1.button("AUTHORIZE", use_container_width=True, type="primary"):
                with open(PASS_FILE, "r") as f:
                    if pwd == f.read().strip():
                        st.session_state.authenticated = True
                        st.rerun()
                    else: st.error("Unauthorized Credentials")
            
            if c2.button("FORGET PASSWORD", use_container_width=True):
                st.session_state.forget_pwd = True
                st.rerun()
                
        st.markdown('</div>', unsafe_allow_html=True)
else:
    apply_custom_styles()
    with st.sidebar:
        st.title("NEURAL HR OS 2026")
        if st.button("🔒 LOCK CONSOLE", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()
        st.divider()
        menu = st.radio("System Modules", ["📺 LIVE VISION", "🔍 SEARCH BY ID", "➕ ENROLL USER", "📝 MODIFY PERSONNEL", "🗑️ TERMINATE ACCESS", "📂 STAFF DIRECTORY", "📊 DAILY REPORTS"])

    if menu == "📺 LIVE VISION":
        st.header("Gateway Security Feed")
        webrtc_streamer(key="vision", video_transformer_factory=FaceRecognitionTransformer, async_processing=True,
                        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

    elif menu == "🔍 SEARCH BY ID":
        st.header("🔍 Personnel Search")
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            if sid:
                try:
                    conn = get_db_connection()
                    df = pd.read_sql_query("SELECT * FROM employees WHERE id = %s", conn, params=(int(sid),))
                    conn.close()
                    if not df.empty:
                        df['is_active'] = df['is_active'].apply(lambda x: "🟢 ACTIVE" if x == 1 else "🔴 TERMINATED")
                        st.dataframe(df, use_container_width=True)
                    else: st.error("⚠️ No person found.")
                except: st.error("Invalid ID")

    elif menu == "➕ ENROLL USER":
        st.header("👤 Biometric Enrollment")
        webrtc_streamer(key="enroll_view", video_transformer_factory=EnrollmentTransformer,
                        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
        with st.form("enroll_form"):
            col1, col2 = st.columns(2)
            fn = col1.text_input("First Name *")
            ln = col2.text_input("Last Name *")
            dept = st.selectbox("Department", ["Technical", "Sales", "HR", "Admin", "Security"])
            email = st.text_input("Email Address")
            contact = st.text_input("Contact Number")
            address = st.text_area("Home Address")
            comp = st.text_input("Compensation / Salary")
            
            photo = st.camera_input("Capture Biometric ID")
            if st.form_submit_button("✨ COMMIT TO CLOUD"):
                if fn and photo:
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("""INSERT INTO employees 
                        (first_name, last_name, dept_name, email, contact, address, compensation, is_active) 
                        VALUES (%s,%s,%s,%s,%s,%s,%s,1) RETURNING id""", 
                        (fn, ln, dept, email, contact, address, comp))
                    nid = cur.fetchone()[0]
                    conn.commit(); cur.close(); conn.close()
                    st.success(f"ID {nid} Secured."); st.balloons()
                else: st.warning("First Name and Photo are required.")

    elif menu == "📝 MODIFY PERSONNEL":
        st.header("📝 Update Records")
        mid = st.number_input("Target ID", min_value=1, step=1)
        if st.button("FETCH PROFILE"):
            conn = get_db_connection(cursor_factory=RealDictCursor)
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id=%s", (mid,))
            res = cur.fetchone()
            cur.close(); conn.close()
            if res: st.session_state['mod_data'] = dict(res)
            else: st.error("Record Not Found")
            
        if 'mod_data' in st.session_state:
            d = st.session_state['mod_data']
            with st.form("mod_form"):
                n_fn = st.text_input("First Name", value=d['first_name'])
                n_email = st.text_input("Email", value=d['email'] or "")
                if st.form_submit_button("💾 OVERWRITE RECORD"):
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("UPDATE employees SET first_name=%s, email=%s WHERE id=%s", (n_fn, n_email, mid))
                    conn.commit(); cur.close(); conn.close()
                    st.success("Synced to Cloud!"); st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        st.header("🚫 Revocation")
        tid = st.number_input("Target ID", min_value=1)
        if st.button("LOCATE"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT first_name, is_active FROM employees WHERE id=%s", (tid,))
            res = cur.fetchone()
            cur.close(); conn.close()
            if res: st.session_state['term_target'] = {"id": tid, "name": res[0], "active": res[1]}
            else: st.error("Not Found")
        if 'term_target' in st.session_state:
            target = st.session_state['term_target']
            st.info(f"Target: {target['name']} | Status: {'🟢 ACTIVE' if target['active']==1 else '🔴 TERMINATED'}")
            if st.button("TOGGLE ACCESS", type="primary"):
                new_val = 0 if target['active'] == 1 else 1
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("UPDATE employees SET is_active=%s WHERE id=%s", (new_val, target['id']))
                conn.commit(); cur.close(); conn.close()
                del st.session_state['term_target']; st.rerun()

    elif menu == "📂 STAFF DIRECTORY":
        st.header("Staff Records")
        conn = get_db_connection(); df = pd.read_sql_query("SELECT * FROM employees ORDER BY id ASC", conn); conn.close()
        df['is_active'] = df['is_active'].apply(lambda x: "🟢 ACTIVE" if x == 1 else "🔴 TERMINATED")
        st.dataframe(df, use_container_width=True)

    elif menu == "📊 DAILY REPORTS":
        st.header("📊 Daily Intelligence")
        today = datetime.now().strftime('%Y-%m-%d')
        conn = get_db_connection()
        att_df = pd.read_sql_query("SELECT a.*, e.first_name FROM attendance a JOIN employees e ON a.emp_id = e.id WHERE a.date = %s", conn, params=(today,))
        active_emp_df = pd.read_sql_query("SELECT id, first_name FROM employees WHERE is_active = 1", conn)
        conn.close()
        
        st.subheader(f"Log for {today}")
        st.dataframe(att_df, use_container_width=True)

        st.divider()
        st.subheader("System Operations")
        c1, c2, c3, c4 = st.columns(4)

        if c1.button("🚨 DETECT ABSENCES", use_container_width=True):
            present_ids = att_df['emp_id'].tolist()
            absent = active_emp_df[~active_emp_df['id'].isin(present_ids)]
            if not absent.empty: st.warning("Absent Personnel:"); st.table(absent)
            else: st.success("All active staff are present.")

        if c2.button("📥 EXPORT TO EXCEL", use_container_width=True):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                att_df.to_excel(writer, index=False)
            st.download_button(label="Download Excel", data=output.getvalue(), file_name=f"Attendance_{today}.xlsx")

        if c3.button("🗑️ WIPE ALL ACTIVE", use_container_width=True, type="primary"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("DELETE FROM employees WHERE is_active = 1")
            conn.commit(); cur.close(); conn.close()
            st.error("Active staff purged from database."); st.rerun()

        if c4.button("📧 DISPATCH TO HR", use_container_width=True):
            if send_security_alert("DAILY DISPATCH", f"Total present today: {len(att_df)}"):
                st.success("Sent to HR Email.")
