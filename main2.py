import streamlit as st
import sqlite3
import os
import re
import csv
import io
from PIL import Image
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# --- Page Config ---
st.set_page_config(page_title="Student Portal", layout="wide")

# --- Upload Directory ---
os.makedirs("uploads", exist_ok=True)

# --- DB Setup ---
DB_PATH = "student_data.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# Full desired schema (column_name: column_definition)
DESIRED_SCHEMA = {
    "uname": "TEXT PRIMARY KEY",
    "pwd": "TEXT",
    "name": "TEXT",
    "father": "TEXT",
    "mother": "TEXT",
    "gender": "TEXT",
    "address": "TEXT",
    "city": "TEXT",
    "state": "TEXT",
    "phone": "TEXT",
    "rrn": "TEXT",
    "enroll": "TEXT",
    "degree": "TEXT",
    "branch": "TEXT",
    "sem": "TEXT",
    "scheme": "TEXT",
    "marks_10th": "TEXT",
    "marks_12th": "TEXT",
    "photo_path": "TEXT",
    "sign_path": "TEXT"
}


def ensure_table_and_columns():
    """Create table if missing and add any missing columns to match DESIRED_SCHEMA."""
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='students'")
    if not c.fetchone():
        cols_def = ", ".join([f"{col} {dtype}" for col, dtype in DESIRED_SCHEMA.items()])
        create_sql = f"CREATE TABLE students ({cols_def})"
        c.execute(create_sql)
        conn.commit()
        return
    c.execute("PRAGMA table_info(students)")
    existing = {row[1] for row in c.fetchall()}
    for col, dtype in DESIRED_SCHEMA.items():
        if col not in existing:
            alter_sql = f"ALTER TABLE students ADD COLUMN {col} {dtype}"
            c.execute(alter_sql)
    conn.commit()


ensure_table_and_columns()

# Create a default admin account if missing (admin has access to Admin Dashboard)
try:
    c.execute("SELECT * FROM students WHERE uname='admin'")
    if not c.fetchone():
        admin_pwd = 'Admin@123'  # change after first login in production
        insert_sql = f"INSERT INTO students ({', '.join(DESIRED_SCHEMA.keys())}) VALUES ({', '.join(['?']*len(DESIRED_SCHEMA))})"
        values = [
            'admin', admin_pwd, 'Administrator', '', '', 'Other', '', '', '', '', '', '', 'Admin', 'Admin', 'NA', 'NA', '', '', '', ''
        ]
        c.execute(insert_sql, tuple(values))
        conn.commit()
except Exception:
    pass

# --- Session Setup ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "login_failed_count" not in st.session_state:
    st.session_state.login_failed_count = 0
if "captcha" not in st.session_state:
    # simple math captcha: store (a, b, answer)
    import random
    a = random.randint(2, 12)
    b = random.randint(2, 12)
    st.session_state.captcha = (a, b, a + b)

# --- Helpers ---

def is_valid_number(num, length=None):
    return bool(num) and num.isdigit() and (len(num) == length if length else True)


def is_valid_name(name):
    return bool(name) and bool(re.fullmatch(r"[A-Za-z ]+", name.strip()))


def is_strong_password(pwd):
    return bool(re.fullmatch(r'(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@#$%^&+=!]).{8,}', pwd))


def is_valid_marks(value):
    return bool(re.fullmatch(r'^\d+(\.\d{1,2})?$', value.strip())) if value and value.strip() else False


def save_file(uploaded_file, filename):
    path = os.path.join("uploads", filename)
    if uploaded_file is None:
        return None
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


# --- Header Function ---

def show_header():
    col1, col2 = st.columns([1, 6])
    with col1:
        logo_path = r"C:\Users\kumaw\PycharmProjects\PythonProject\logo1.png"
        if os.path.exists(logo_path):
            st.image(logo_path, width=140)
        else:
            st.markdown("<div style='padding:10px; color:gray;'>[Logo not found]</div>", unsafe_allow_html=True)
    with col2:
        st.markdown("<h1 style='margin-bottom: 0;'>🎓 Student Portal</h1>", unsafe_allow_html=True)
        st.markdown("<p style='font-size:14px; margin-top:0;'>Joshi's and Kumawat University </p>", unsafe_allow_html=True)
    st.markdown("---")


# --- Admin Utilities ---

def export_all_users_csv():
    c.execute("SELECT * FROM students")
    rows = c.fetchall()
    c.execute("PRAGMA table_info(students)")
    cols = [r[1] for r in c.fetchall()]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    for r in rows:
        writer.writerow(r)
    return output.getvalue().encode('utf-8')


def import_users_from_csv(file_bytes):
    """CSV must have headers matching DESIRED_SCHEMA keys (order not important). Returns (imported, errors)."""
    errors = []
    imported = 0
    decoded = file_bytes.read().decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))
    required_cols = set(DESIRED_SCHEMA.keys())
    if not required_cols.issubset(set(reader.fieldnames)):
        errors.append("CSV missing required columns. Required columns: " + ",".join(sorted(required_cols)))
        return imported, errors
    insert_sql = f"INSERT INTO students ({', '.join(DESIRED_SCHEMA.keys())}) VALUES ({', '.join(['?']*len(DESIRED_SCHEMA))})"
    for i, row in enumerate(reader, start=2):
        try:
            values = [row.get(k, '') for k in DESIRED_SCHEMA.keys()]
            c.execute(insert_sql, tuple(values))
            imported += 1
        except sqlite3.IntegrityError as e:
            errors.append(f"Row {i}: {e}")
        except Exception as e:
            errors.append(f"Row {i}: {e}")
    conn.commit()
    return imported, errors


# --- Login and Registration ---

def login_register():
    show_header()
    tab = st.radio("Select Option", ["Login", "Register"])

    if tab == "Register":
        st.subheader("📝 Student Registration")
        with st.form("register_form"):
            uname = st.text_input("Username")
            pwd = st.text_input("Password", type="password", help="uppercase and lowercase letters, numbers, symbols")
            name = st.text_input("Student Name")
            father = st.text_input("Father's Name")
            mother = st.text_input("Mother's Name")
            gender = st.selectbox("Gender", ["Male", "Female", "Other"])
            address = st.text_area("Address")
            city = st.text_input("City")
            state = st.selectbox("State", ["Select", "Rajasthan", "Karnataka", "Delhi", "Tamil Nadu"])
            phone = st.text_input("Phone Number")
            rrn = st.text_input("Alternative Number")
            enroll = st.text_input("Enrollment Number")
            degree = st.selectbox("Degree", ["Select", "B.Tech", "MCA", "MBA"])
            branch = st.selectbox("Branch", ["Select", "CSE", "AI/ML", "ECE", "ME"])
            sem = st.selectbox("Semester", ["Select", "I", "II", "III", "IV", "V", "VI"])
            scheme = st.selectbox("Year", ["Select", 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029])
            marks_10th = st.text_input("10th Marks (Percentage / CGPA / SGPA)")
            marks_12th = st.text_input("12th Marks (Percentage / CGPA / SGPA)")
            photo = st.file_uploader("Upload Photo", type=["jpg", "jpeg", "png"])
            sign = st.file_uploader("Upload Signature", type=["jpg", "jpeg", "png"])
            submit = st.form_submit_button("Register")

            if submit:
                # same validation as original but with clearer immediate errors
                missing_fields = not all([
                    uname, pwd, name, father, mother, gender, address,
                    city, (state and state != "Select"), phone, rrn, enroll,
                    (degree and degree != "Select"), (branch and branch != "Select"),
                    (sem and sem != "Select"), (scheme and scheme != "Select"),
                    marks_10th, marks_12th, photo, sign
                ])
                if missing_fields:
                    st.error("All fields are required. Check highlighted fields.")
                elif not all(map(is_valid_name, [name, father, mother, city])):
                    st.error("Names and city must contain only letters and spaces.")
                elif not is_valid_number(phone, 10):
                    st.error("Phone must be exactly 10 digits.")
                elif not is_strong_password(pwd):
                    st.error("Password must be strong (A-Z, a-z, 0-9, symbol, min 8 chars).")
                elif not is_valid_marks(marks_10th) or not is_valid_marks(marks_12th):
                    st.error("Marks must be numeric (decimals allowed), e.g. 85 or 85.50")
                else:
                    photo_path = save_file(photo, f"{uname}_photo.png")
                    sign_path = save_file(sign, f"{uname}_sign.png")
                    columns = list(DESIRED_SCHEMA.keys())
                    placeholders = ",".join(["?"] * len(columns))
                    insert_sql = f"INSERT INTO students ({', '.join(columns)}) VALUES ({placeholders})"
                    values = [
                        uname, pwd, name, father, mother, gender,
                        address, city, state, phone, rrn, enroll,
                        degree, branch, sem, scheme, marks_10th, marks_12th,
                        photo_path, sign_path
                    ]
                    try:
                        c.execute(insert_sql, tuple(values))
                        conn.commit()
                        st.success("✅ Registered successfully. Please log in.")
                    except sqlite3.IntegrityError:
                        st.error("Username already exists. Choose a different username.")
                    except Exception as e:
                        st.error(f"Error saving data: {e}")

    elif tab == "Login":
        st.subheader("🔐 Login")
        with st.form("login_form"):
            uname = st.text_input("Username", key="login_uname")
            pwd = st.text_input("Password", type="password", key="login_pwd")

            # --- ALWAYS SHOW CAPTCHA ---
            a, b, ans = st.session_state.captcha
            user_ans = st.text_input(f"Captcha: What is {a} + {b}?", key="captcha_input")

            submit_login = st.form_submit_button("Login")

            if submit_login:
                # Validate captcha first
                try:
                    captcha_ok = int(user_ans) == ans
                except Exception:
                    captcha_ok = False

                if not captcha_ok:
                    st.session_state.login_failed_count += 1
                    st.error("Captcha incorrect. Please try again.")
                    # regenerate captcha for next attempt
                    import random
                    a = random.randint(2, 12)
                    b = random.randint(2, 12)
                    st.session_state.captcha = (a, b, a + b)
                else:
                    # captcha passed, now check credentials
                    c.execute("SELECT * FROM students WHERE uname=? AND pwd=?", (uname, pwd))
                    user = c.fetchone()
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.user_data = user
                        st.session_state.login_failed_count = 0
                        st.success(f"✅ Welcome {user[2]}!")
                        # regenerate captcha for next time
                        import random
                        a = random.randint(2, 12)
                        b = random.randint(2, 12)
                        st.session_state.captcha = (a, b, a + b)
                        st.rerun()
                    else:
                        st.session_state.login_failed_count += 1
                        st.error("❌ Invalid credentials.")
                        # regenerate captcha for next attempt
                        import random
                        a = random.randint(2, 12)
                        b = random.randint(2, 12)
                        st.session_state.captcha = (a, b, a + b)


# --- Dashboard ---

def dashboard(user):
    show_header()
    st.sidebar.title("📁 Tabs")

    # admin sees extra options
    is_admin_user = (user[0] == 'admin')
    base_options = ["Home", "About Me", "College Detail", "Photo & Signature", "Download PDF"]
    admin_options = ["Admin Dashboard"] if is_admin_user else []
    option = st.sidebar.radio("Go to", base_options + admin_options + ["Logout"])

    if option == "Logout":
        st.session_state.logged_in = False
        st.session_state.user_data = None
        st.success("You are logged out.")
        st.rerun()

    c.execute("PRAGMA table_info(students)")
    col_info = c.fetchall()
    col_names = [row[1] for row in col_info]
    user_dict = dict(zip(col_names, user))

    if option == "Home":
        st.title("🎓 Student Dashboard")
        col1, col2 = st.columns([1, 2])
        with col1:
            photo = user_dict.get("photo_path")
            sign = user_dict.get("sign_path")
            if photo and os.path.exists(photo):
                st.image(photo, width=150, caption=f"Photo - {user_dict.get('name')}")
            else:
                st.info("Photo not found")
            if sign and os.path.exists(sign):
                st.image(sign, width=150, caption=f"Signature - {user_dict.get('name')}")
            else:
                st.info("Signature not found")
        with col2:
            st.markdown(f"""
                **Name:** {user_dict.get('name', '')}  
                **RRN:** {user_dict.get('rrn', '')}  
                **Enrollment No.:** {user_dict.get('enroll', '')}  
                **Branch:** {user_dict.get('branch', '')}  
                **Semester:** {user_dict.get('sem', '')}  
                **10th Marks:** {user_dict.get('marks_10th', '')}  
                **12th Marks:** {user_dict.get('marks_12th', '')}  
            """)

    elif option == "About Me":
        st.header("👤 About Me")
        st.markdown(f"""
            **Name:** {user_dict.get('name', '')}  
            **Father's Name:** {user_dict.get('father', '')}  
            **Mother's Name:** {user_dict.get('mother', '')}  
            **Gender:** {user_dict.get('gender', '')}  
            **Phone:** {user_dict.get('phone', '')}  
            **Address:** {user_dict.get('address', '')}, {user_dict.get('city', '')}, {user_dict.get('state', '')}  
        """)

    elif option == "College Detail":
        st.header("🏫 College Details")
        st.markdown(f"""
            **Alternative number:** {user_dict.get('rrn', '')}  
            **Enrollment No.:** {user_dict.get('enroll', '')}  
            **Degree:** {user_dict.get('degree', '')}  
            **Branch:** {user_dict.get('branch', '')}  
            **Semester:** {user_dict.get('sem', '')}  
            **Year:** {user_dict.get('scheme', '')}  
            **10th Marks:** {user_dict.get('marks_10th', '')}  
            **12th Marks:** {user_dict.get('marks_12th', '')}  
        """)

    elif option == "Photo & Signature":
        st.header("📷 Photo and Signature")
        photo = user_dict.get("photo_path")
        sign = user_dict.get("sign_path")
        if photo and os.path.exists(photo):
            st.image(photo, width=200, caption=f"Student Photo - {user_dict.get('name')}")
        else:
            st.info("Photo not found")
        if sign and os.path.exists(sign):
            st.image(sign, width=200, caption=f"Student Signature - {user_dict.get('name')}")
        else:
            st.info("Signature not found")

    elif option == "Download PDF":
        st.header("📄 Download Details as PDF")
        if st.button("Generate PDF"):
            pdf_buffer = BytesIO()
            c_pdf = canvas.Canvas(pdf_buffer, pagesize=letter)

            # --- Logo ---
            logo_path = r"C:\Users\kumaw\PycharmProjects\PythonProject\logo1.png"
            if os.path.exists(logo_path):
                try:
                    c_pdf.drawImage(ImageReader(logo_path), 40, 720, width=60, height=60, preserveAspectRatio=True)
                except Exception:
                    pass

            c_pdf.setFont("Helvetica-Bold", 16)
            c_pdf.drawCentredString(300, 750, "Joshi's and Kumawat University")

            # --- Photo & Signature row (separate row/column) ---
            # Coordinates and sizes
            top_y = 700  # start y (below title)
            box_height = 140
            box_width = 220
            gap = 20
            left_x = 40
            right_x = left_x + box_width + gap

            # Draw boxes (borders)
            c_pdf.rect(left_x, top_y - box_height, box_width, box_height)   # Photo box
            c_pdf.rect(right_x, top_y - box_height, box_width, box_height)  # Signature box

            # Add labels under each box
            c_pdf.setFont("Helvetica-Bold", 10)
            c_pdf.drawString(left_x, top_y - box_height - 12, "Photo")
            c_pdf.drawString(right_x, top_y - box_height - 12, "Signature")

            # Try to draw photo and signature images (scale to fit keeping aspect ratio)
            photo_path = user_dict.get("photo_path")
            sign_path = user_dict.get("sign_path")

            def draw_image_in_box(img_path, box_x, box_y_top, box_w, box_h, alt_text="Image not found"):
                if img_path and os.path.exists(img_path):
                    try:
                        with Image.open(img_path) as im:
                            # maintain aspect ratio and fit inside box with some padding
                            max_w = box_w - 8
                            max_h = box_h - 8
                            im_w, im_h = im.size
                            ratio = min(max_w / im_w, max_h / im_h, 1.0)
                            disp_w = im_w * ratio
                            disp_h = im_h * ratio
                            # center image inside box
                            x_pos = box_x + (box_w - disp_w) / 2
                            y_pos = box_y_top - box_h + (box_h - disp_h) / 2
                            c_pdf.drawImage(ImageReader(im), x_pos, y_pos, width=disp_w, height=disp_h, preserveAspectRatio=True)
                            return
                    except Exception:
                        pass
                # if we reach here, image missing or failed -> put alt text centered
                c_pdf.setFont("Helvetica", 9)
                text_x = box_x + 6
                text_y = box_y_top - box_h / 2
                c_pdf.drawString(text_x, text_y, alt_text)

            # draw the photo and signature inside their boxes
            draw_image_in_box(photo_path, left_x, top_y, box_width, box_height, alt_text="Photo not found")
            draw_image_in_box(sign_path, right_x, top_y, box_width, box_height, alt_text="Signature not found")

            # --- Table of fields below the image row ---
            fields = [
                "Name", "Father", "Mother", "Gender", "Address", "City", "State",
                "Phone", "Alternative number", "Enroll",
                "Degree", "Branch", "Sem", "Year", "10th Marks", "12th Marks"
            ]

            # mapping: human label -> actual stored value from user_dict (use actual column names)
            mapping = {
                "Name": user_dict.get("name", ""),
                "Father": user_dict.get("father", ""),
                "Mother": user_dict.get("mother", ""),
                "Gender": user_dict.get("gender", ""),
                "Address": user_dict.get("address", ""),
                "City": user_dict.get("city", ""),
                "State": user_dict.get("state", ""),
                "Phone": user_dict.get("phone", ""),
                "Alternative number": user_dict.get("rrn", ""),
                "Enroll": user_dict.get("enroll", ""),
                "Degree": user_dict.get("degree", ""),
                "Branch": user_dict.get("branch", ""),
                "Sem": user_dict.get("sem", ""),
                "Year": user_dict.get("scheme", ""),
                "10th Marks": user_dict.get("marks_10th", ""),
                "12th Marks": user_dict.get("marks_12th", "")
            }

            table_x = 40
            table_y_start = top_y - box_height - 40  # start the table below the image row
            row_height = 26
            col_widths = [140, 360]
            num_rows = len(fields)
            table_width = col_widths[0] + col_widths[1]

            # Draw horizontal lines
            for i in range(num_rows + 1):
                y = table_y_start - i * row_height
                c_pdf.line(table_x, y, table_x + table_width, y)

            # Draw vertical lines (left border, middle, right border)
            c_pdf.line(table_x, table_y_start, table_x, table_y_start - num_rows * row_height)
            c_pdf.line(table_x + col_widths[0], table_y_start, table_x + col_widths[0], table_y_start - num_rows * row_height)
            c_pdf.line(table_x + table_width, table_y_start, table_x + table_width, table_y_start - num_rows * row_height)

            c_pdf.setFont("Helvetica-Bold", 11)
            text_padding_x = 6
            text_padding_y = 7
            for idx, label in enumerate(fields):
                y_top = table_y_start - idx * row_height
                y_text = y_top - row_height + text_padding_y
                c_pdf.setFont("Helvetica-Bold", 10)
                c_pdf.drawString(table_x + text_padding_x, y_text + 4, f"{label}:")
                value = str(mapping.get(label, ""))
                c_pdf.setFont("Helvetica", 10)
                max_chars_per_line = 55
                lines = []
                if value:
                    words = value.split()
                    current_line = ""
                    for w in words:
                        if len(current_line) + len(w) + 1 <= max_chars_per_line:
                            current_line = (current_line + " " + w).strip()
                        else:
                            lines.append(current_line)
                            current_line = w
                    if current_line:
                        lines.append(current_line)
                else:
                    lines = [""]

                for li, vline in enumerate(lines):
                    line_y = y_top - (li + 1) * 12
                    bottom_limit = table_y_start - num_rows * row_height
                    if line_y < bottom_limit + 6:
                        vline = vline[:40] + "..."
                    c_pdf.drawString(table_x + col_widths[0] + text_padding_x, line_y + 4, vline)

            c_pdf.save()
            pdf_buffer.seek(0)
            st.download_button("📥 Download PDF", data=pdf_buffer.getvalue(), file_name="student_detail.pdf", mime="application/pdf")

    elif option == "Admin Dashboard":
        st.header("🛠️ Admin Dashboard")
        st.markdown("Manage users, bulk import/export and perform admin actions.")

        tab_admin = st.tabs(["User List", "Bulk Import", "Export All", "Admin Actions"])

        # --- User List ---
        with tab_admin[0]:
            st.subheader("All Registered Users")
            c.execute("SELECT * FROM students")
            rows = c.fetchall()
            c.execute("PRAGMA table_info(students)")
            cols = [r[1] for r in c.fetchall()]
            # simple table
            if rows:
                st.write(cols)
                for r in rows:
                    st.write(dict(zip(cols, r)))
            else:
                st.info("No users found.")

        # --- Bulk Import ---
        with tab_admin[1]:
            st.subheader("Bulk Import from CSV")
            st.markdown("CSV must contain headers exactly matching database columns. Example template available in Export All tab.")
            uploaded_csv = st.file_uploader("Upload CSV file (UTF-8)", type=["csv"])
            if uploaded_csv is not None:
                imported, errors = import_users_from_csv(uploaded_csv)
                st.success(f"Imported: {imported}")
                if errors:
                    st.error("Some rows failed to import. See details below.")
                    for e in errors:
                        st.write(e)

        # --- Export All ---
        with tab_admin[2]:
            st.subheader("Export / Template")
            csv_bytes = export_all_users_csv()
            st.download_button("📥 Download All Users (CSV)", data=csv_bytes, file_name="all_users.csv", mime="text/csv")
            # also provide a template with headers only
            template = io.StringIO()
            writer = csv.writer(template)
            writer.writerow(list(DESIRED_SCHEMA.keys()))
            st.download_button("📥 Download Template CSV", data=template.getvalue().encode('utf-8'), file_name="students_template.csv", mime="text/csv")

        # --- Admin Actions ---
        with tab_admin[3]:
            st.subheader("Actions")
            st.markdown("Delete a user or reset a password.")
            del_user = st.text_input("Username to delete")
            if st.button("Delete User"):
                if del_user:
                    if del_user == 'admin':
                        st.error("Cannot delete the admin user.")
                    else:
                        c.execute("DELETE FROM students WHERE uname=?", (del_user,))
                        conn.commit()
                        st.success(f"Deleted user: {del_user}")
                else:
                    st.error("Enter a username to delete.")

            rst_user = st.text_input("Username to reset password")
            new_pwd = st.text_input("New password", type='password')
            if st.button("Reset Password"):
                if rst_user and new_pwd:
                    if rst_user == 'admin':
                        st.error("Reset admin password directly in DB or change after login.")
                    else:
                        c.execute("UPDATE students SET pwd=? WHERE uname=?", (new_pwd, rst_user))
                        conn.commit()
                        st.success(f"Password reset for {rst_user}")
                else:
                    st.error("Provide username and new password.")


# --- Run App ---
if st.session_state.logged_in and st.session_state.user_data:
    dashboard(st.session_state.user_data)
else:
    login_register()
