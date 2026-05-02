class FaceRecognitionTransformer(VideoProcessorBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.last_alert = {}
        # CACHE: تحديث بيانات الموظفين كل 5 ثوانٍ فقط بدلاً من كل إطار (Frame)
        self.users = []
        self.last_db_fetch = 0

    def get_users(self):
        """جلب البيانات من قاعدة البيانات بفاصل زمني لتقليل الضغط"""
        if time.time() - self.last_db_fetch > 5:
            conn = sqlite3.connect(SQL_DB)
            self.users = conn.execute("SELECT id, first_name, is_active, shift_start, grace_period FROM employees").fetchall()
            conn.close()
            self.last_db_fetch = time.time()
        return self.users

    def mark_attendance(self, emp_id, name, shift_start, grace):
        """تسجيل الحضور (دالة مساعدة كما هي)"""
        now = datetime.now()
        today, current_time = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
        conn = sqlite3.connect(SQL_DB)
        exists = conn.execute("SELECT id FROM attendance WHERE emp_id=? AND date=?", (emp_id, today)).fetchone()
        if not exists:
            try:
                s_dt, c_dt = datetime.strptime(shift_start, '%H:%M'), datetime.strptime(current_time, '%H:%M')
                late = max(0, int((c_dt - s_dt).total_seconds() / 60) - grace)
                penalty = f"{late}m Late" if late > 0 else "On Time"
            except:
                late, penalty = 0, "N/A"
            conn.execute(
                "INSERT INTO attendance (emp_id, name, date, clock_in, late_minutes, penalty, status) VALUES (?,?,?,?,?,?,?)",
                (emp_id, name, today, current_time, late, penalty, "Office"))
            conn.commit()
        else:
            conn.execute("UPDATE attendance SET clock_out=? WHERE emp_id=? AND date=?", (current_time, emp_id, today))
            conn.commit()
        conn.close()

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)

        # استدعاء البيانات المخزنة مؤقتاً
        users = self.get_users()

        for (x, y, w, h) in faces:
            color, label = (0, 255, 255), "IDENTIFYING..."

            for eid, fname, active, shift, grace in users:
                # منطق التحقق من الحالة
                if active == 0:
                    color, label = (0, 0, 255), f"⚠️ DENIED: {fname}"
                    if eid not in self.last_alert or (time.time() - self.last_alert[eid]) > 3600:
                        send_security_notification(f"Alert: {fname} attempting access", f"Personnel {fname} (ID:{eid}) tried to access the system.")
                        self.last_alert[eid] = time.time()
                else:
                    color, label = (0, 255, 0), f"VERIFIED: {fname}"
                    # ملاحظة: قد ترغب في إضافة شرط هنا لعدم تكرار التحديث كل جزء من الثانية
                    self.mark_attendance(eid, fname, shift, grace)

            cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
            cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        return av.VideoFrame.from_ndarray(img, format="bgr24")
