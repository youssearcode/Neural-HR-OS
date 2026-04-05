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
    except Exception as e:
        st.error(f"Email Alert Failed: {e}")
        return False

# --- 5. TRANSFORMERS (OPTIMIZED FOR SPEED) ---
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
        self.last_alert = {}
        self.frame_count = 0

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
        self.frame_count += 1
        img = frame.to_ndarray(format="bgr24")
        
        # Optimization: Process every 2nd frame to increase FPS
        if self.frame_count % 2 != 0:
            return img

        # Optimization: Resize for faster processing
        small_img = cv2.resize(img, (0, 0), fx=0.5, fy=0.5)
        gray = cv2.cvtColor(small_img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.2, 4)
        
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id, first_name, is_active, shift_start, grace_period FROM employees")
        users = cur.fetchall()
        cur.close(); conn.close()

        for (x, y, w, h) in faces:
            # Scale coordinates back up
            x, y, w, h = x*2, y*2, w*2, h*2
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

# --- 6. MAIN APP ---
if "authenticated" not in st.session_state: st.session_state.authenticated = False

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
                else: st.error("Unauthorized Credentials")
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
                    target_id = int(sid)
                    conn = get_db_connection()
                    df = pd.read_sql_query("SELECT * FROM employees WHERE id = %s", conn, params=(target_id,))
                    conn.close()
                    if not df.empty:
                        # Logic Update: 1 -> Green Active, 0 -> Red Terminated
                        df['is_active'] = df['is_active'].apply(lambda x: "🟢 ACTIVE" if x == 1 else "🔴 TERMINATED")
                        st.dataframe(df, use_container_width=True)
                    else: 
                        st.error("⚠️ No person found in the database with this ID.")
                except ValueError:
                    st.error("Please enter a valid numeric ID")

    elif menu == "➕ ENROLL USER":
        st.header("👤 Biometric Enrollment")
        webrtc_streamer(key="enroll_view", video_transformer_factory=EnrollmentTransformer,
                        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
        
        with st.form("enroll_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                fn, ln = st.text_input("First Name *"), st.text_input("Last Name *")
                dept = st.selectbox("Dept", ["Technical", "Sales", "HR", "Admin", "Security"])
            with c2:
                cont, email = st.text_input("Contact"), st.text_input("Email")
                shift, grace = st.text_input("Shift", "09:00"), st.number_input("Grace", 15)
            with c3:
                comp, perf = st.text_input("Salary"), st.selectbox("Performance", ["Excellent", "Good", "Average"])
                addr = st.text_area("Address")
            photo = st.camera_input("Capture Biometric ID")
            if st.form_submit_button("✨ COMMIT TO CLOUD"):
                if fn and photo:
                    conn = get_db_connection(); cur = conn.cursor()
                    cur.execute("""INSERT INTO employees (first_name, last_name, dept_name, address, email, contact, compensation, performance, shift_start, grace_period, is_active) 
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1) RETURNING id""",
                                (fn, ln, dept, addr, email, cont, comp, perf, shift, grace))
                    nid = cur.fetchone()[0]; folder = f"{nid}_{fn}"
                    cur.execute("UPDATE employees SET folder_name=%s WHERE id=%s", (folder, nid))
                    conn.commit(); cur.close(); conn.close()
                    st.success(f"✅ Enrollment Complete: ID {nid} Secured."); st.balloons()

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
            if res: 
                st.session_state['term_target'] = {"id": tid, "name": res[0], "active": res[1]}
            else:
                st.error("⚠️ No person found in the database with this ID.")
        
        if 'term_target' in st.session_state:
            target = st.session_state['term_target']
            status_label = "🟢 ACTIVE" if target['active'] == 1 else "🔴 TERMINATED"
            st.info(f"Target: {target['name']} | Status: {status_label}")
            if st.button("TOGGLE ACCESS", type="primary"):
                new_s = 1 if target['active'] == 0 else 0
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("UPDATE employees SET is_active=%s WHERE id=%s", (new_s, target['id']))
                conn.commit(); cur.close(); conn.close()
                st.warning(f"Access Updated for {target['name']}"); del st.session_state['term_target']; st.rerun()

    elif menu == "📂 STAFF DIRECTORY":
        st.header("Staff Records")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM employees ORDER BY id ASC", conn)
        conn.close()
        # Logic Update: Display labels instead of integers
        df['is_active'] = df['is_active'].apply(lambda x: "🟢 ACTIVE" if x == 1 else "🔴 TERMINATED")
        st.dataframe(df, use_container_width=True)

    elif menu == "📊 DAILY REPORTS":
        st.header("📊 Intelligence Dashboard")
        today = datetime.now().strftime('%Y-%m-%d')
        conn = get_db_connection()
        q = "SELECT a.*, e.first_name, e.dept_name FROM attendance a JOIN employees e ON a.emp_id = e.id WHERE a.date = %s"
        df = pd.read_sql_query(q, conn, params=(today,))
        all_emp_df = pd.read_sql_query("SELECT id, first_name, dept_name FROM employees WHERE is_active = 1", conn)
        conn.close()

        if not df.empty:
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Total Present", len(df))
            with c2: 
                late_count = len(df[df['late_minutes'] > 0])
                st.metric("Late Arrivals", late_count)
            with c3: 
                occ = (len(df) / len(all_emp_df) * 100) if not all_emp_df.empty else 0
                st.metric("Occupancy", f"{occ:.1f}%")
            
            st.divider()
            st.dataframe(df, use_container_width=True)
            
            # --- ACTION GRID ---
            st.subheader("System Operations")
            col1, col2, col3 = st.columns(3)
            col4, col5, col6 = st.columns(3)

            if col1.button("🚨 DETECT ABSENCES", use_container_width=True):
                present_ids = df['emp_id'].tolist()
                absent_df = all_emp_df[~all_emp_df['id'].isin(present_ids)]
                st.warning("Personnel Not Logged In:")
                st.table(absent_df)

            if col2.button("📥 EXPORT TO EXCEL", use_container_width=True):
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Daily_Report')
                st.download_button(label="Download Excel", data=output.getvalue(), file_name=f"Attendance_{today}.xlsx")

            # Logic Update: Delete all active persons button
            if col3.button("🗑️ WIPE ALL ACTIVE", use_container_width=True, type="primary"):
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("DELETE FROM employees WHERE is_active = 1")
                conn.commit(); cur.close(); conn.close()
                st.error("All Active Personnel have been purged from database."); st.rerun()

            if col4.button("📧 DISPATCH TO HR", use_container_width=True):
                if send_security_alert("DAILY DISPATCH", f"Report for {today}. Staff present: {len(df)}"):
                    st.success("Sent to HR.")

        else:
            st.info("No logs for today. Looking for active staff...")
            if st.button("🗑️ WIPE ALL ACTIVE", use_container_width=True, type="primary"):
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("DELETE FROM employees WHERE is_active = 1")
                conn.commit(); cur.close(); conn.close()
                st.error("Purged Active Personnel."); st.rerun()
