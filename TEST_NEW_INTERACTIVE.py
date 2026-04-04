import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import av
import cv2
import os
import sqlite3
import pandas as pd
import numpy as np
import base64
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import time

# --- 1. CONFIG & AUTH SETTINGS ---
st.set_page_config(page_title="NEURAL HR OS 2026", layout="wide", page_icon="🛡️")

# --- 2. DATABASE & MIGRATION ---
SQL_DB = "HR_Database.db"

def init_sql():
    conn = sqlite3.connect(SQL_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS employees
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     first_name TEXT, last_name TEXT, dept_name TEXT,
                     address TEXT, email TEXT, contact TEXT,
                     emergency_contact TEXT, compensation TEXT,
                     performance TEXT, folder_name TEXT,
                     shift_start TEXT DEFAULT "09:00",
                     grace_period INTEGER DEFAULT 15,
                     current_status TEXT DEFAULT "Office",
                     is_active INTEGER DEFAULT 1)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS attendance
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     emp_id INTEGER, name TEXT, date TEXT,
                     clock_in TEXT, clock_out TEXT,
                     late_minutes INTEGER, penalty TEXT,
                     status TEXT)''')

    cursor = conn.execute("PRAGMA table_info(employees)")
    columns = [column[1] for column in cursor.fetchall()]
    if "is_active" not in columns:
        try:
            conn.execute("ALTER TABLE employees ADD COLUMN is_active INTEGER DEFAULT 1")
            st.toast("Database Migrated: Added 'is_active' column.")
        except:
            pass
    conn.commit()
    conn.close()

init_sql()

# --- 3. SYSTEM GLOBALS ---
EMAIL_USER = "mohamedauoup@gmail.com"
EMAIL_PASS = "xjpwurhrozvybini"
HR_RECIPIENT = "mohamedauoup@gmail.com"
PASS_FILE = "hr_password.txt"
MASTER_KEY = "1234567"
DB_PATH = "attendance_data"

if not os.path.exists(PASS_FILE):
    with open(PASS_FILE, "w") as f: f.write("123")

# --- 4. UTILITIES ---
@st.cache_data
def get_video_base64(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
    except:
        return None

def apply_custom_styles():
    video_path = "1.mp4"
    video_base64 = get_video_base64(video_path)
    video_html = f'<video autoplay loop muted playsinline id="bg-video"><source src="data:video/mp4;base64,{video_base64}" type="video/mp4"></video>' if video_base64 else ""

    st.markdown(
        f"""
        {video_html}
        <style>
        #bg-video {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; object-fit: cover; z-index: -1; filter: brightness(1.0); opacity: 1.0; }}
        .stApp {{ background: transparent !important; }}
        [data-testid="stHeader"] {{ background: transparent !important; }}
        [data-testid="stSidebar"] {{ background-color: rgba(0, 0, 0, 0.4) !important; backdrop-filter: blur(15px); }}
        div[data-testid="stForm"], .stDataFrame, .main-card {{
            background-color: rgba(0, 0, 0, 0.3) !important; border-radius: 15px; padding: 25px; backdrop-filter: blur(12px);
            border: 1px solid rgba(0, 210, 255, 0.2); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6); margin-bottom: 20px;
        }}
        h1, h2, h3, p, label, .stMarkdown {{ color: #ffffff !important; text-shadow: 1px 1px 3px rgba(0,0,0,0.8); }}
        .stButton>button {{ background-color: rgba(0, 210, 255, 0.3) !important; border: 1px solid #00d2ff !important; color: white !important; border-radius: 10px; }}
        </style>
        """, unsafe_allow_html=True
    )

def send_security_alert(subject, body):
    try:
        msg = MIMEText(f"NEURAL HR OS 2026 - SECURITY LOG\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{body}")
        msg['Subject'] = f"🛡️ SYSTEM ALERT: {subject}"
        msg['From'], msg['To'] = EMAIL_USER, HR_RECIPIENT
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email Alert Failed: {e}")
        return False

# --- 5. TRANSFORMERS ---
class EnrollmentTransformer(VideoTransformerBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
            cv2.putText(img, "SCANNING BIOMETRICS...", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        return img

class FaceRecognitionTransformer(VideoTransformerBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.last_alert = {}

    def mark_attendance(self, emp_id, name, shift_start, grace):
        now = datetime.now()
        today, current_time = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
        conn = sqlite3.connect(SQL_DB)
        exists = conn.execute("SELECT id FROM attendance WHERE emp_id=? AND date=?", (emp_id, today)).fetchone()
        if not exists:
            try:
                s_dt, c_dt = datetime.strptime(shift_start, '%H:%M'), datetime.strptime(current_time, '%H:%M')
                late = max(0, int((c_dt - s_dt).total_seconds() / 60) - grace)
                penalty = f"{late}m Late" if late > 0 else "On Time"
            except: late, penalty = 0, "N/A"
            conn.execute("INSERT INTO attendance (emp_id, name, date, clock_in, late_minutes, penalty, status) VALUES (?,?,?,?,?,?,?)",
                        (emp_id, name, today, current_time, late, penalty, "Office"))
            conn.commit()
        else:
            conn.execute("UPDATE attendance SET clock_out=? WHERE emp_id=? AND date=?", (current_time, emp_id, today))
            conn.commit()
        conn.close()

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        conn = sqlite3.connect(SQL_DB)
        users = conn.execute("SELECT id, first_name, is_active, shift_start, grace_period FROM employees").fetchall()
        conn.close()
        for (x, y, w, h) in faces:
            color, label = (0, 255, 255), "IDENTIFYING..."
            for eid, fname, active, shift, grace in users:
                if active == 0:
                    color, label = (0, 0, 255), f"⚠️ ACCESS DENIED: {fname}"
                    if eid not in self.last_alert or (time.time() - self.last_alert[eid]) > 3600:
                        send_security_alert("BANNED ACCESS ATTEMPT", f"Terminated employee '{fname}' (ID: {eid}) was detected.")
                        self.last_alert[eid] = time.time()
                else:
                    color, label = (0, 255, 0), f"VERIFIED: {fname}"
                    self.mark_attendance(eid, fname, shift, grace)
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
            cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return img

# --- 6. MAIN APP LOGIC ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    apply_custom_styles()
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown('<div class="main-card" style="margin-top: 15%;">', unsafe_allow_html=True)
        st.title("🛡️ NEURAL GATEWAY")
        pwd = st.text_input("HR Security Password", type="password")
        
        if st.button("AUTHORIZE ACCESS", use_container_width=True, type="primary"):
            with open(PASS_FILE, "r") as f:
                if pwd == f.read().strip():
                    st.session_state.authenticated = True
                    st.rerun()
                else: 
                    st.error("Unauthorized Credentials")

        with st.expander("Forgot System Password?"):
            mk = st.text_input("Master Reset Key", type="password", key="m_key")
            new_p = st.text_input("New Secure Password", type="password", key="n_pass")
            
            if st.button("OVERRIDE & RESET"):
                if not mk or not new_p:
                    st.warning("Please enter BOTH the Master Key and your New Password.")
                elif mk == MASTER_KEY:
                    alert_msg = (
                        f"ALERT: A manual system override was performed.\n"
                        f"Action: Password Reset\n"
                        f"New HR Password Set To: {new_p}\n"
                        f"Authorized by: Master Key Protocol"
                    )
                    with st.spinner("Notifying HR and resetting system..."):
                        success = send_security_alert("MASTER KEY OVERRIDE DETECTED", alert_msg)
                        if success:
                            with open(PASS_FILE, "w") as f:
                                f.write(new_p)
                            st.success("System Reset Successful. Alert Sent.")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Security Alert failed to send. Reset blocked for safety.")
                else:
                    st.error("Invalid Master Key.")
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # --- LOGGED IN AREA ---
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
                        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
                        media_stream_constraints={"video": True, "audio": False})

    elif menu == "🔍 SEARCH BY ID":
        st.header("🔍 Personnel Search")
        sid = st.text_input("Enter Target ID")
        if st.button("RUN QUERY"):
            if sid:
                conn = sqlite3.connect(SQL_DB)
                df = pd.read_sql_query("SELECT * FROM employees WHERE CAST(id AS TEXT) = ?", conn, params=(sid,))
                conn.close()
                if not df.empty: st.dataframe(df, use_container_width=True)
                else: st.error("ID Not Found")
            else: st.warning("Please enter an ID first.")

    elif menu == "➕ ENROLL USER":
        st.header("👤 Detailed Biometric Enrollment")
        webrtc_streamer(key="enroll_cam", video_transformer_factory=EnrollmentTransformer, async_processing=True,
                        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
                        media_stream_constraints={"video": True, "audio": False})
        with st.form("enroll_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                fn, ln = st.text_input("First Name *"), st.text_input("Last Name *")
                dept = st.selectbox("Dept", ["Technical", "Sales", "HR", "Admin", "Security"])
                email = st.text_input("Email")
            with c2:
                cont, econt = st.text_input("Contact"), st.text_input("Emergency Contact")
                shift, grace = st.text_input("Shift (HH:MM)", "09:00"), st.number_input("Grace", 15)
            with c3:
                comp, perf = st.text_input("Salary/Comp"), st.selectbox("Performance", ["Excellent", "Good", "Average"])
                status, addr = st.selectbox("Status", ["Office", "WFH", "Sick"]), st.text_area("Address")
            photo = st.camera_input("Capture Biometric ID")
            if st.form_submit_button("✨ COMMIT TO DATABASE"):
                if fn and photo:
                    conn = sqlite3.connect(SQL_DB); cur = conn.cursor()
                    cur.execute("INSERT INTO employees (first_name, last_name, dept_name, address, email, contact, emergency_contact, compensation, performance, shift_start, grace_period, current_status, is_active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                                (fn, ln, dept, addr, email, cont, econt, comp, perf, shift, grace, status))
                    nid = cur.lastrowid; folder = f"{nid}_{fn}"
                    cur.execute("UPDATE employees SET folder_name=? WHERE id=?", (folder, nid))
                    conn.commit(); conn.close()
                    os.makedirs(os.path.join(DB_PATH, folder), exist_ok=True)
                    cv2.imwrite(os.path.join(DB_PATH, folder, f"{fn}.jpg"), cv2.imdecode(np.frombuffer(photo.read(), np.uint8), 1))
                    st.success(f"✅ Enrollment Complete: {fn} assigned ID: {nid}"); st.balloons()

    elif menu == "📝 MODIFY PERSONNEL":
        st.header("📝 Update Personnel Records")
        mid = st.number_input("Target ID", min_value=1, step=1)
        if st.button("FETCH PROFILE"):
            conn = sqlite3.connect(SQL_DB); conn.row_factory = sqlite3.Row
            res = conn.execute("SELECT * FROM employees WHERE id=?", (mid,)).fetchone()
            conn.close()
            if res: st.session_state['mod_data'] = dict(res)
            else: st.error("Record Not Found")
        if 'mod_data' in st.session_state:
            d = st.session_state['mod_data']
            with st.form("mod_form"):
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    n_fn, n_ln = st.text_input("First Name", value=str(d.get('first_name', ""))), st.text_input("Last Name", value=str(d.get('last_name', "")))
                    n_dept, n_email = st.selectbox("Dept", ["Technical", "Sales", "HR", "Admin", "Security"]), st.text_input("Email", value=str(d.get('email', "")))
                with mc2:
                    n_cont, n_econt = st.text_input("Contact", value=str(d.get('contact', ""))), st.text_input("Emergency", value=str(d.get('emergency_contact', "")))
                    n_shift, n_grace = st.text_input("Shift Start", value=str(d.get('shift_start', "09:00"))), st.number_input("Grace Period", value=int(d.get('grace_period', 15)))
                with mc3:
                    n_comp, n_perf = st.text_input("Compensation", value=str(d.get('compensation', ""))), st.selectbox("Performance", ["Excellent", "Good", "Average", "Needs Improvement"])
                    n_status, n_addr = st.selectbox("Current Status", ["Office", "WFH", "Sick", "Vacation"]), st.text_area("Address", value=str(d.get('address', "")))
                if st.form_submit_button("💾 OVERWRITE RECORD"):
                    conn = sqlite3.connect(SQL_DB)
                    conn.execute("UPDATE employees SET first_name=?, last_name=?, dept_name=?, address=?, email=?, contact=?, emergency_contact=?, compensation=?, performance=?, shift_start=?, grace_period=?, current_status=? WHERE id=?",
                                 (n_fn, n_ln, n_dept, n_addr, n_email, n_cont, n_econt, n_comp, n_perf, n_shift, n_grace, n_status, mid))
                    conn.commit(); conn.close()
                    st.success(f"💾 ID {mid} synced!"); st.rerun()

    elif menu == "🗑️ TERMINATE ACCESS":
        st.header("🚫 Security Access Revocation")
        tid = st.number_input("Target Personnel ID", min_value=1)
        if st.button("LOCATE PERSONNEL"):
            conn = sqlite3.connect(SQL_DB)
            res = conn.execute("SELECT first_name, is_active FROM employees WHERE id=?", (tid,)).fetchone()
            conn.close()
            if res: st.session_state['term_target'] = {"id": tid, "name": res[0], "active": res[1]}
        if 'term_target' in st.session_state:
            target = st.session_state['term_target']
            btn = "🔄 REINSTATE ACCESS" if target['active'] == 0 else "❗ TERMINATE ACCESS"
            if st.button(btn, use_container_width=True, type="primary"):
                new_s = 1 if target['active'] == 0 else 0
                conn = sqlite3.connect(SQL_DB)
                conn.execute("UPDATE employees SET is_active=? WHERE id=?", (new_s, target['id']))
                conn.commit(); conn.close()
                st.warning(f"⚠️ ACCESS UPDATED: {target['name']} is now {'ACTIVE' if new_s == 1 else 'BANNED'}")
                del st.session_state['term_target']; time.sleep(1); st.rerun()

    elif menu == "📂 STAFF DIRECTORY":
        st.header("Staff Records Overview")
        conn = sqlite3.connect(SQL_DB)
        st.dataframe(pd.read_sql_query("SELECT * FROM employees", conn), use_container_width=True)
        conn.close()

    elif menu == "📊 DAILY REPORTS":
        st.header("Daily Attendance Intelligence")
        today = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(SQL_DB)
        # UPDATED: Added a.clock_out and strictly filtered for e.is_active = 1
        q = f"""
            SELECT 
                a.emp_id, 
                e.first_name, 
                e.dept_name, 
                a.clock_in, 
                a.clock_out, 
                a.late_minutes, 
                a.penalty 
            FROM attendance a 
            JOIN employees e ON a.emp_id = e.id 
            WHERE a.date = '{today}' AND e.is_active = 1
        """
        df = pd.read_sql_query(q, conn)
        conn.close()
        if not df.empty: 
            st.dataframe(df, use_container_width=True)
        else: 
            st.info("No active logs for today.")
