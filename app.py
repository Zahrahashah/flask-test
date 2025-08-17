from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import mysql.connector
from db import get_connection
import time
import base64
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import uuid
import logging
import re
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.secret_key = 'secret123'

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure upload folders
UPLOAD_FOLDER_EVENTS = os.path.join(app.root_path, 'static', 'Uploads', 'events')
UPLOAD_FOLDER_COURSES = os.path.join(app.root_path, 'static', 'Uploads', 'courses')
UPLOAD_FOLDER_ADMISSIONS = os.path.join(app.root_path, 'static', 'Uploads', 'admissions')

app.config['UPLOAD_FOLDER_EVENTS'] = UPLOAD_FOLDER_EVENTS
app.config['UPLOAD_FOLDER_COURSES'] = UPLOAD_FOLDER_COURSES
app.config['UPLOAD_FOLDER_ADMISSIONS'] = UPLOAD_FOLDER_ADMISSIONS
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

# Ensure upload folders exist with proper permissions
for folder in [UPLOAD_FOLDER_EVENTS, UPLOAD_FOLDER_COURSES, UPLOAD_FOLDER_ADMISSIONS]:
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
        os.chmod(folder, 0o755)

# Custom Jinja2 filter for datetime formatting
def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return value
    return value.strftime(format)

app.jinja_env.filters['datetimeformat'] = datetimeformat

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Validate CNIC format (e.g., 12345-1234567-1)
def validate_cnic(cnic):
    return re.match(r'^\d{5}-\d{7}-\d{1}$', cnic) is not None

# Validate phone format (e.g., +923123456789)
def validate_phone(phone):
    return re.match(r'^\+92\d{10}$', phone) is not None

# Initialize database tables
def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS popups
                      (id INTEGER PRIMARY KEY AUTO_INCREMENT,
                       title VARCHAR(255),
                       message TEXT NOT NULL,
                       image_url VARCHAR(255),
                       show_until TEXT,
                       type TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       student_id INT(11),
                       date DATE,
                       status VARCHAR(20),
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS students
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       name VARCHAR(100) NOT NULL,
                       age INT,
                       guardian_id INT(11),
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS contacts
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       name VARCHAR(100) NOT NULL,
                       email VARCHAR(100) NOT NULL,
                       subject VARCHAR(200),
                       message TEXT,
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       is_read BOOLEAN DEFAULT FALSE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS progress_reports
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       student_id INT(11),
                       subject VARCHAR(100),
                       marks INT,
                       comments TEXT,
                       report_date DATE,
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS staff
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       designation VARCHAR(100) NOT NULL,
                       bps_grade VARCHAR(10) NOT NULL,
                       quantity INT NOT NULL)''')
    # Add missing columns if table exists
    cursor.execute("SHOW COLUMNS FROM staff LIKE 'bps_grade'")
    if not cursor.fetchone():
        cursor.execute('''ALTER TABLE staff ADD COLUMN bps_grade VARCHAR(10) NOT NULL AFTER designation''')
    cursor.execute("SHOW COLUMNS FROM staff LIKE 'quantity'")
    if not cursor.fetchone():
        cursor.execute('''ALTER TABLE staff ADD COLUMN quantity INT NOT NULL AFTER bps_grade''')
    # Remove obsolete columns
    cursor.execute("SHOW COLUMNS FROM staff LIKE 'name'")
    if cursor.fetchone():
        cursor.execute('''ALTER TABLE staff DROP COLUMN name''')
    cursor.execute("SHOW COLUMNS FROM staff LIKE 'qualification'")
    if cursor.fetchone():
        cursor.execute('''ALTER TABLE staff DROP COLUMN qualification''')
    cursor.execute("SHOW COLUMNS FROM staff LIKE 'photo_url'")
    if cursor.fetchone():
        cursor.execute('''ALTER TABLE staff DROP COLUMN photo_url''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS guardians
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       full_name VARCHAR(100) NOT NULL,
                       email VARCHAR(100) NOT NULL UNIQUE,
                       password VARCHAR(255) NOT NULL,
                       phone VARCHAR(15),
                       cnic VARCHAR(15),
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admissions
                  (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                   student_name VARCHAR(100) NOT NULL,
                   cnic VARCHAR(15) NOT NULL,
                   dob DATE,
                   gender VARCHAR(10),
                   age INT,
                   phone VARCHAR(15),
                   address TEXT,
                   student_occupation VARCHAR(100),
                   parent_name VARCHAR(100),
                   parent_cnic VARCHAR(15),
                   parent_phone VARCHAR(15),
                   parent_occupation VARCHAR(100),
                   num_siblings INT,
                   sibling_disability VARCHAR(100),
                   guardian_name VARCHAR(100),
                   guardian_phone VARCHAR(15),
                   disability_certificate VARCHAR(255),
                   disability_name VARCHAR(100),
                   medical_history TEXT,
                   regular_medication TEXT,
                   assistive_device VARCHAR(100),
                   epilepsy VARCHAR(10),
                   drug_addiction VARCHAR(10),
                   assistant VARCHAR(10),
                   communicable_disease TEXT,
                   education_level VARCHAR(100),
                   documents VARCHAR(255),
                   course VARCHAR(100),
                   admission_type VARCHAR(20),
                   duration_stay INT,
                   pick_drop VARCHAR(100),
                   affidavit VARCHAR(10),
                   admission_date DATE,
                   photo VARCHAR(255),
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # Dynamically add missing columns to admissions table
    cursor.execute("SHOW COLUMNS FROM admissions")
    existing_columns = [col[0] for col in cursor.fetchall()]
    required_columns = {
        'phone': 'VARCHAR(15) AFTER age',
        'address': 'TEXT AFTER phone',
        'student_occupation': 'VARCHAR(100) AFTER address',
        'parent_name': 'VARCHAR(100) AFTER student_occupation',
        'parent_cnic': 'VARCHAR(15) AFTER parent_name',
        'parent_phone': 'VARCHAR(15) AFTER parent_cnic',
        'parent_occupation': 'VARCHAR(100) AFTER parent_phone',
        'num_siblings': 'INT AFTER parent_occupation',
        'sibling_disability': 'VARCHAR(100) AFTER num_siblings',
        'guardian_name': 'VARCHAR(100) AFTER sibling_disability',
        'guardian_phone': 'VARCHAR(15) AFTER guardian_name',
        'disability_certificate': 'VARCHAR(255) AFTER guardian_phone',
        'disability_name': 'VARCHAR(100) AFTER disability_certificate',
        'medical_history': 'TEXT AFTER disability_name',
        'regular_medication': 'TEXT AFTER medical_history',
        'assistive_device': 'VARCHAR(100) AFTER regular_medication',
        'epilepsy': 'VARCHAR(10) AFTER assistive_device',
        'drug_addiction': 'VARCHAR(10) AFTER epilepsy',
        'assistant': 'VARCHAR(10) AFTER drug_addiction',
        'communicable_disease': 'TEXT AFTER assistant',
        'education_level': 'VARCHAR(100) AFTER communicable_disease',
        'documents': 'VARCHAR(255) AFTER education_level',
        'course': 'VARCHAR(100) AFTER documents',
        'admission_type': 'VARCHAR(20) AFTER course',
        'duration_stay': 'INT AFTER admission_type',
        'pick_drop': 'VARCHAR(100) AFTER duration_stay',
        'affidavit': 'VARCHAR(10) AFTER pick_drop',
        'admission_date': 'DATE AFTER affidavit',
        'photo': 'VARCHAR(255) AFTER admission_date'
    }
    for col, definition in required_columns.items():
        if col not in existing_columns:
            cursor.execute(f"ALTER TABLE admissions ADD COLUMN {col} {definition}")
    cursor.execute("SHOW COLUMNS FROM admissions LIKE 'photo'")
    if not cursor.fetchone():
        cursor.execute('''ALTER TABLE admissions ADD COLUMN photo VARCHAR(255)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS courses
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       course_id VARCHAR(36) NOT NULL,
                       name VARCHAR(100) NOT NULL,
                       description TEXT,
                       duration VARCHAR(50),
                       level VARCHAR(50),
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       image_url VARCHAR(255))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS events
                      (id INT(11) PRIMARY KEY AUTO_INCREMENT,
                       title VARCHAR(100) NOT NULL,
                       date DATE,
                       description TEXT,
                       image_url VARCHAR(255),
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    cursor.close()
    conn.close()

# Public Routes
@app.route('/')
def index():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM events ORDER BY date DESC LIMIT 3")
        events = cursor.fetchall()
        cursor.execute("SELECT * FROM courses")
        courses = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching data: {str(e)}', 'error')
        logging.error(f"Index fetch error: {str(e)}")
        events = []
        courses = []
    finally:
        cursor.close()
        conn.close()
    return render_template('index.html', events=events, courses=courses)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/courses')
def courses():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM courses")
        courses = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching courses: {str(e)}', 'error')
        logging.error(f"Courses fetch error: {str(e)}")
        courses = []
    finally:
        cursor.close()
        conn.close()
    return render_template('courses.html', courses=courses)

@app.route('/programs')
def programs():
    return render_template('programs.html')

@app.route('/team')
def team():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM staff")
        staff = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching staff data: {str(e)}', 'error')
        logging.error(f"Team fetch error: {str(e)}")
        staff = []
    finally:
        cursor.close()
        conn.close()
    return render_template('team.html', staff=staff)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/facilities')
def facilities():
    return render_template('facilities.html')

@app.route('/admissions')
def admissions():
    return render_template('admissions.html')

@app.route('/apply_now')
def apply_now():
    if session.get('user_type') != 'guardian':
        flash('Please sign up or log in as a guardian to apply.', 'error')
        return redirect(url_for('guardian_signup_page'))
    return render_template('apply_now.html', today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/events')
def events():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM events ORDER BY date DESC")
        events = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching events: {str(e)}', 'error')
        logging.error(f"Events fetch error: {str(e)}")
        events = []
    finally:
        cursor.close()
        conn.close()
    return render_template('events.html', events=events)

@app.route('/contact_submit', methods=['POST'])
def contact_submit():
    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')
    if not all([name, email, message]):
        flash('Please fill all required fields.', 'error')
        return redirect(url_for('contact'))
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""INSERT INTO contacts (name, email, subject, message, is_read)
                         VALUES (%s, %s, %s, %s, %s)""", (name, email, subject, message, False))
        conn.commit()
        flash('Contact form submitted successfully!', 'success')
    except Exception as e:
        flash(f'Error submitting contact form: {str(e)}', 'error')
        logging.error(f"Contact submit error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('contact'))

# Guardian Routes
@app.route('/guardian_signup', methods=['GET'])
def guardian_signup_page():
    return render_template('guardian_signup.html')

@app.route('/guardian_signup', methods=['POST'])
def guardian_signup():
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    password = request.form.get('password')
    phone = request.form.get('phone')
    cnic = request.form.get('cnic')
    if not all([full_name, email, password]):
        flash('Please fill all required fields.', 'error')
        return redirect(url_for('guardian_signup_page'))
    if cnic and not validate_cnic(cnic):
        flash('Invalid CNIC format. Use 12345-1234567-1.', 'error')
        return redirect(url_for('guardian_signup_page'))
    if phone and not validate_phone(phone):
        flash('Invalid phone format. Use +923123456789.', 'error')
        return redirect(url_for('guardian_signup_page'))
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""INSERT INTO guardians (full_name, email, password, phone, cnic)
                         VALUES (%s, %s, %s, %s, %s)""", (full_name, email, password, phone, cnic))
        conn.commit()
        flash('Signup successful! Please log in.', 'success')
    except Exception as e:
        flash(f'Signup failed: {str(e)}', 'error')
        logging.error(f"Signup error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('guardian_login_page'))

@app.route('/guardian', methods=['GET'])
def guardian_login_page():
    return render_template('guardian_login.html')

@app.route('/guardian/login', methods=['POST'])
def guardian_login():
    email = request.form.get('email')
    password = request.form.get('password')
    if not all([email, password]):
        flash('Please provide email and password.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, name, email, password FROM admins WHERE email = %s", (email,))
        admin = cursor.fetchone()
        if admin and admin['password'] == password:
            session['user_type'] = 'admin'
            session['user_name'] = admin['name']
            session['user_email'] = admin['email']
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        cursor.execute("SELECT id, full_name, email, password FROM guardians WHERE email = %s", (email,))
        guardian = cursor.fetchone()
        if guardian and guardian['password'] == password:
            session['user_type'] = 'guardian'
            session['user_name'] = guardian['full_name']
            session['user_email'] = guardian['email']
            session['guardian_id'] = guardian['id']
            flash('Guardian login successful!', 'success')
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'error')
    except Exception as e:
        flash(f'Login error: {str(e)}', 'error')
        logging.error(f"Login error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('guardian_login_page'))

@app.route('/forgot_password', methods=['GET'])
def forgot_password_page():
    return render_template('forgot_password.html')

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    email = request.form.get('email')
    if not email:
        flash('Please provide an email address.', 'error')
        return redirect(url_for('forgot_password_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT email, name FROM admins WHERE email = %s", (email,))
        admin = cursor.fetchone()
        cursor.execute("SELECT email, full_name FROM guardians WHERE email = %s", (email,))
        guardian = cursor.fetchone()
        if admin or guardian:
            token = base64.b64encode(f"{email}:{int(time.time())}".encode()).decode()
            session['reset_token'] = token
            session['reset_email'] = email
            session['user_type'] = 'admin' if admin else 'guardian'
            flash('Password reset link sent! Check your email.', 'success')
        else:
            flash('Email not found.', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        logging.error(f"Forgot password error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('forgot_password_page'))

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if 'reset_token' not in session or session['reset_token'] != token:
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('guardian_login_page'))
    if request.method == 'GET':
        return render_template('reset_password.html', token=token)
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    email = session.get('reset_email')
    user_type = session.get('user_type')
    if not password or password != confirm_password:
        flash('Passwords do not match or are empty.', 'error')
        return redirect(url_for('reset_password', token=token))
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if user_type == 'admin':
            cursor.execute("UPDATE admins SET password = %s WHERE email = %s", (password, email))
        else:
            cursor.execute("UPDATE guardians SET password = %s WHERE email = %s", (password, email))
        conn.commit()
        flash('Password reset successfully! Please log in.', 'success')
        session.pop('reset_token', None)
        session.pop('reset_email', None)
        session.pop('user_type', None)
    except Exception as e:
        flash(f'Error resetting password: {str(e)}', 'error')
        logging.error(f"Reset password error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('guardian_login_page'))

@app.route('/guardian_dashboard')
def guardian_dashboard():
    if session.get('user_type') != 'guardian':
        flash('Please log in as a guardian.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT title, date FROM events WHERE date >= CURDATE() ORDER BY date ASC LIMIT 3")
        events = cursor.fetchall()
        cursor.execute("""
                       SELECT s.id, s.name, s.age
                       FROM students s
                       JOIN guardians g ON s.guardian_id = g.id
                       WHERE g.id = %s
                       """, (session.get('guardian_id'),))
        children = cursor.fetchall()
        cursor.execute("""
                       SELECT a.id, s.name AS student_name, a.date, a.status
                       FROM attendance a
                       JOIN students s ON a.student_id = s.id
                       JOIN guardians g ON s.guardian_id = g.id
                       WHERE g.id = %s
                       ORDER BY a.date DESC LIMIT 3
                       """, (session.get('guardian_id'),))
        attendance = cursor.fetchall()
        cursor.execute("""
                       SELECT p.id, s.name AS student_name, p.subject, p.marks, p.report_date
                       FROM progress_reports p
                       JOIN students s ON p.student_id = s.id
                       JOIN guardians g ON s.guardian_id = g.id
                       WHERE g.id = %s
                       ORDER BY p.report_date DESC LIMIT 3
                       """, (session.get('guardian_id'),))
        progress_reports = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching dashboard data: {str(e)}', 'error')
        logging.error(f"Dashboard error: {str(e)}")
        events = []
        children = []
        attendance = []
        progress_reports = []
    finally:
        cursor.close()
        conn.close()
    return render_template('guardian_dashboard.html',
                           guardian_name=session.get('user_name'),
                           events=events,
                           children=children,
                           attendance=attendance,
                           progress_reports=progress_reports)

@app.route('/guardian_settings', methods=['GET', 'POST'])
def guardian_settings():
    if session.get('user_type') != 'guardian':
        flash('Please log in as a guardian.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        cnic = request.form.get('cnic')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not full_name:
            flash('Full name is required.', 'error')
            return redirect(url_for('guardian_settings'))
        if password and password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('guardian_settings'))
        if cnic and not validate_cnic(cnic):
            flash('Invalid CNIC format. Use 12345-1234567-1.', 'error')
            return redirect(url_for('guardian_settings'))
        if phone and not validate_phone(phone):
            flash('Invalid phone format. Use +923123456789.', 'error')
            return redirect(url_for('guardian_settings'))
        try:
            update_fields = ['full_name = %s', 'phone = %s', 'cnic = %s']
            update_values = [full_name, phone or None, cnic or None]
            if password:
                update_fields.append('password = %s')
                update_values.append(password)
            update_values.append(session.get('user_email'))
            query = f"UPDATE guardians SET {', '.join(update_fields)} WHERE email = %s"
            cursor.execute(query, update_values)
            conn.commit()
            if full_name != session.get('user_name'):
                session['user_name'] = full_name
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating profile: {str(e)}', 'error')
            logging.error(f"Settings update error: {str(e)}")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('guardian_settings'))
    try:
        cursor.execute("SELECT full_name, email, phone, cnic FROM guardians WHERE email = %s",
                       (session.get('user_email'),))
        guardian = cursor.fetchone()
    except Exception as e:
        flash(f'Error fetching settings: {str(e)}', 'error')
        logging.error(f"Settings fetch error: {str(e)}")
        guardian = None
    finally:
        cursor.close()
        conn.close()
    return render_template('guardian_settings.html', guardian=guardian)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('guardian_login_page'))

# Admin Routes
@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) as count FROM courses")
        course_count = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM staff")
        staff_count = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM students")
        student_count = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM events")
        event_count = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE is_read = FALSE")
        contact_count = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM admissions")
        admission_count = cursor.fetchone()['count']
    except Exception as e:
        flash(f'Error fetching dashboard data: {str(e)}', 'error')
        logging.error(f"Admin dashboard error: {str(e)}")
        course_count = staff_count = student_count = event_count = contact_count = admission_count = 0
    finally:
        cursor.close()
        conn.close()
    return render_template('admin_dashboard.html',
                           course_count=course_count,
                           staff_count=staff_count,
                           student_count=student_count,
                           event_count=event_count,
                           contact_count=contact_count,
                           admission_count=admission_count)


@app.route('/api/courses_events', methods=['GET'])
def api_courses_events():
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get the last 6 months
        today = datetime.now()
        months = []
        courses_data = []
        events_data = []
        for i in range(5, -1, -1):  # Last 6 months, including current
            month_date = today - relativedelta(months=i)
            month_name = month_date.strftime('%b %Y')
            month_num = month_date.month
            year = month_date.year
            months.append(month_name)
            # Courses
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM courses
                WHERE MONTH(created_at) = %s AND YEAR(created_at) = %s
            """, (month_num, year))
            courses_data.append(cursor.fetchone()['count'])
            # Events
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM events
                WHERE MONTH(created_at) = %s AND YEAR(created_at) = %s
            """, (month_num, year))
            events_data.append(cursor.fetchone()['count'])
        logging.info(f"Months: {months}, Courses data: {courses_data}, Events data: {events_data}")
        return jsonify({
            'success': True,
            'months': months,
            'courses': courses_data,
            'events': events_data
        })
    except Exception as e:
        logging.error(f"API courses_events error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/activity_breakdown', methods=['GET'])
def api_activity_breakdown():
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) as count FROM courses")
        courses = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM events")
        events = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM staff")
        staff = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM contacts")
        contacts = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM admissions")
        admissions = cursor.fetchone()['count']
        return jsonify({
            'success': True,
            'courses': courses,
            'events': events,
            'staff': staff,
            'contacts': contacts,
            'admissions': admissions
        })
    except Exception as e:
        logging.error(f"API activity_breakdown error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/admission/<int:id>', methods=['GET'])
def api_admission(id):
    if session.get('user_type') != 'admin':
        logging.warning(f"Unauthorized access attempt to /api/admission/{id}, user_type: {session.get('user_type')}")
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    try:
        conn = get_connection()
        if not conn.is_connected():
            logging.error("Database connection failed")
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor(dictionary=True)
        logging.debug(f"Executing query for admission ID {id}")
        cursor.execute("""
            SELECT id, student_name, cnic, dob, gender, age, phone, address, student_occupation,
                   parent_name, parent_cnic, parent_phone, parent_occupation, num_siblings, sibling_disability,
                   guardian_name, guardian_phone, disability_certificate, disability_name, medical_history,
                   regular_medication, assistive_device, epilepsy, drug_addiction, assistant, communicable_disease,
                   education_level, documents, course, admission_type, duration_stay, pick_drop, affidavit,
                   admission_date, photo, created_at
            FROM admissions
            WHERE id = %s
        """, (id,))
        admission = cursor.fetchone()
        if admission:
            # Format dates for display
            admission['dob'] = admission['dob'].strftime('%Y-%m-%d') if admission['dob'] else 'N/A'
            admission['admission_date'] = admission['admission_date'].strftime('%Y-%m-%d') if admission['admission_date'] else 'N/A'
            admission['created_at'] = admission['created_at'].strftime('%Y-%m-%d %H:%M:%S') if admission['created_at'] else 'N/A'
            # Handle documents
            admission['documents'] = admission['documents'].split(',') if admission['documents'] else []
            # Ensure all fields are strings or 'N/A'
            for key in admission:
                if admission[key] is None:
                    admission[key] = 'N/A'
            logging.info(f"Successfully fetched admission ID {id}: {admission}")
            return jsonify({'success': True, 'admission': admission})
        else:
            logging.warning(f"No admission found for ID {id}")
            return jsonify({'success': False, 'error': 'Admission not found'}), 404
    except mysql.connector.Error as db_error:
        logging.error(f"Database error for admission ID {id}: {str(db_error)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Database error: {str(db_error)}'}), 500
    except Exception as e:
        logging.error(f"Unexpected error for admission ID {id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/add_course', methods=['POST'])
def add_course():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    try:
        name = request.form.get('name')
        description = request.form.get('description')
        duration = request.form.get('duration')
        level = request.form.get('level')
        if not all([name, description, duration, level]):
            flash('All fields are required.', 'error')
            return redirect(url_for('admin_courses'))
        created_at = datetime.utcnow()
        course_id = str(uuid.uuid4())
        image_url = None

        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                filename = f"course_{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER_COURSES'], filename)
                file.save(file_path)
                image_url = f"Uploads/courses/{filename}"
                logging.debug(f"Course image saved: {file_path}")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO courses (course_id, name, description, duration, level, created_at, image_url) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (course_id, name, description, duration, level, created_at, image_url))
        conn.commit()
        flash('Course added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding course: {str(e)}', 'error')
        logging.error(f"Add course error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_courses'))

@app.route('/edit_course/<course_id>', methods=['GET', 'POST'])
def edit_course(course_id):
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            duration = request.form.get('duration')
            level = request.form.get('level')
            if not all([name, description, duration, level]):
                flash('All fields are required.', 'error')
                return redirect(url_for('admin_courses'))
            image_url = request.form.get('existing_image_url')

            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    if image_url and os.path.exists(os.path.join('static', image_url)):
                        os.remove(os.path.join('static', image_url))
                    filename = secure_filename(file.filename)
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    filename = f"course_{timestamp}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER_COURSES'], filename)
                    file.save(file_path)
                    image_url = f"Uploads/courses/{filename}"
                    logging.debug(f"Course image updated: {file_path}")

            cursor.execute(
                'UPDATE courses SET name = %s, description = %s, duration = %s, level = %s, image_url = %s WHERE course_id = %s',
                (name, description, duration, level, image_url, course_id))
            conn.commit()
            flash('Course updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating course: {str(e)}', 'error')
            logging.error(f"Edit course error: {str(e)}")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_courses'))
    try:
        cursor.execute('SELECT * FROM courses WHERE course_id = %s', (course_id,))
        course = cursor.fetchone()
        if not course:
            flash('Course not found.', 'error')
            return redirect(url_for('admin_courses'))
        return render_template('admin_edit_course.html', course=course)
    except Exception as e:
        flash(f'Error fetching course: {str(e)}', 'error')
        logging.error(f"Fetch course error: {str(e)}")
        return redirect(url_for('admin_courses'))
    finally:
        cursor.close()
        conn.close()

@app.route('/delete_course', methods=['POST'])
def delete_course():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    try:
        course_id = request.form.get('course_id')
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT image_url FROM courses WHERE course_id = %s', (course_id,))
        course = cursor.fetchone()
        if course and course['image_url'] and os.path.exists(os.path.join('static', course['image_url'])):
            os.remove(os.path.join('static', course['image_url']))
        cursor.execute('DELETE FROM courses WHERE course_id = %s', (course_id,))
        conn.commit()
        flash('Course deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting course: {str(e)}', 'error')
        logging.error(f"Delete course error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_courses'))



@app.route('/admin_courses')
def admin_courses():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM courses")
        courses = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching courses: {str(e)}', 'error')
        logging.error(f"Fetch courses error: {str(e)}")
        courses = []
    finally:
        cursor.close()
        conn.close()
    return render_template('admin_courses.html', courses=courses)

@app.route('/admin_staff')
def admin_staff():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'danger')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, designation, bps_grade, quantity FROM staff")
        staff = cursor.fetchall()
        for member in staff:
            member['designation'] = member['designation'] or 'N/A'
            member['bps_grade'] = member['bps_grade'] or 'N/A'
            member['quantity'] = member['quantity'] if member['quantity'] is not None else 'N/A'
    except Exception as e:
        flash(f'Error fetching staff: {str(e)}', 'danger')
        logging.error(f"Fetch staff error: {str(e)}")
        staff = []
    finally:
        cursor.close()
        conn.close()
    return render_template('admin_staff.html', staff=staff)

@app.route('/staff/add', methods=['POST'])
def add_staff():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'danger')
        return redirect(url_for('guardian_login_page'))
    try:
        designation = request.form.get('designation')
        bps_grade = request.form.get('bps_grade')
        quantity = request.form.get('quantity')
        if not all([designation, bps_grade, quantity]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('admin_staff'))
        try:
            quantity = int(quantity)
            if quantity < 1:
                flash('Quantity must be at least 1.', 'danger')
                return redirect(url_for('admin_staff'))
        except ValueError:
            flash('Quantity must be a valid number.', 'danger')
            return redirect(url_for('admin_staff'))
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO staff (designation, bps_grade, quantity) VALUES (%s, %s, %s)',
                       (designation, bps_grade, quantity))
        conn.commit()
        flash('Staff added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding staff: {str(e)}', 'danger')
        logging.error(f"Add staff error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_staff'))

@app.route('/staff/edit/<int:id>', methods=['GET', 'POST'])
def edit_staff(id):
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'danger')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        try:
            designation = request.form.get('designation')
            bps_grade = request.form.get('bps_grade')
            quantity = request.form.get('quantity')
            if not all([designation, bps_grade, quantity]):
                flash('All fields are required.', 'danger')
                return redirect(url_for('admin_staff'))
            try:
                quantity = int(quantity)
                if quantity < 1:
                    flash('Quantity must be at least 1.', 'danger')
                    return redirect(url_for('admin_staff'))
            except ValueError:
                flash('Quantity must be a valid number.', 'danger')
                return redirect(url_for('admin_staff'))
            cursor.execute(
                'UPDATE staff SET designation = %s, bps_grade = %s, quantity = %s WHERE id = %s',
                (designation, bps_grade, quantity, id))
            conn.commit()
            flash('Staff updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating staff: {str(e)}', 'danger')
            logging.error(f"Edit staff error: {str(e)}")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_staff'))
    try:
        cursor.execute('SELECT id, designation, bps_grade, quantity FROM staff WHERE id = %s', (id,))
        staff_member = cursor.fetchone()
        if not staff_member:
            flash('Staff member not found.', 'danger')
            return redirect(url_for('admin_staff'))
        return render_template('edit_staff.html', staff=staff_member)
    except Exception as e:
        flash(f'Error fetching staff: {str(e)}', 'danger')
        logging.error(f"Fetch staff error: {str(e)}")
        return redirect(url_for('admin_staff'))
    finally:
        cursor.close()
        conn.close()

@app.route('/staff/delete/<int:id>', methods=['POST'])
def delete_staff(id):
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'danger')
        return redirect(url_for('guardian_login_page'))
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM staff WHERE id = %s', (id,))
        if cursor.rowcount == 0:
            flash('Staff member not found.', 'danger')
        else:
            conn.commit()
            flash('Staff deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting staff: {str(e)}', 'danger')
        logging.error(f"Delete staff error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_staff'))

@app.route('/admin_contacts')
def admin_contacts():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, name, email, subject, message, created_at, is_read FROM contacts ORDER BY created_at DESC")
        contacts = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching contacts: {str(e)}', 'error')
        logging.error(f"Fetch contacts error: {str(e)}")
        contacts = []
    finally:
        cursor.close()
        conn.close()
    return render_template('admin_contacts.html', contacts=contacts)

@app.route('/mark_contact_read/<int:id>', methods=['POST'])
def mark_contact_read(id):
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE contacts SET is_read = TRUE WHERE id = %s", (id,))
        conn.commit()
        flash('Message marked as read.', 'success')
        return jsonify({'success': True, 'message': 'Message marked as read.'})
    except Exception as e:
        flash(f'Error marking contact as read: {str(e)}', 'error')
        logging.error(f"Mark contact read error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/mark_contact_unread/<int:id>', methods=['POST'])
def mark_contact_unread(id):
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE contacts SET is_read = FALSE WHERE id = %s", (id,))
        conn.commit()
        flash('Message marked as unread.', 'success')
        return jsonify({'success': True, 'message': 'Message marked as unread.'})
    except Exception as e:
        flash(f'Error marking contact as unread: {str(e)}', 'error')
        logging.error(f"Mark contact unread error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_unread_count', methods=['GET'])
def get_unread_count():
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM contacts WHERE is_read = FALSE")
        unread_count = cursor.fetchone()[0]
        return jsonify({'success': True, 'unread_count': unread_count})
    except Exception as e:
        logging.error(f"Get unread count error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/delete_contact', methods=['POST'])
def delete_contact():
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    try:
        id = request.json.get('id')
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM contacts WHERE id = %s', (id,))
        conn.commit()
        flash('Message deleted successfully!', 'success')
        return jsonify({'success': True, 'message': 'Message deleted successfully!'})
    except Exception as e:
        flash(f'Error deleting contact: {str(e)}', 'error')
        logging.error(f"Delete contact error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin_popups')
def admin_popups():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM popups")
        popups = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching popups: {str(e)}', 'error')
        logging.error(f"Fetch popups error: {str(e)}")
        popups = []
    finally:
        cursor.close()
        conn.close()
    return render_template('admin_popups.html', popups=popups)

@app.route('/add_popup', methods=['POST'])
def add_popup():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    try:
        title = request.form.get('title')
        message = request.form.get('message')
        show_until = request.form.get('show_until')
        popup_type = request.form.get('type')
        if not message:
            flash('Message is required.', 'error')
            return redirect(url_for('admin_popups'))
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                filename = f"popup_{timestamp}_{filename}"
                upload_folder = os.path.join(app.root_path, 'static', 'Uploads', 'popups')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder, exist_ok=True)
                    os.chmod(upload_folder, 0o755)
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)
                image_url = f"Uploads/popups/{filename}"
                logging.debug(f"Popup image saved: {file_path}")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO popups (title, message, image_url, show_until, type) VALUES (%s, %s, %s, %s, %s)',
                       (title, message, image_url, show_until, popup_type))
        conn.commit()
        flash('Popup added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding popup: {str(e)}', 'error')
        logging.error(f"Add popup error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_popups'))

@app.route('/edit_popup/<int:id>', methods=['GET', 'POST'])
def edit_popup(id):
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            message = request.form.get('message')
            show_until = request.form.get('show_until')
            popup_type = request.form.get('type')
            if not message:
                flash('Message is required.', 'error')
                return redirect(url_for('admin_popups'))
            image_url = request.form.get('existing_image_url')
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    if image_url and os.path.exists(os.path.join(app.root_path, 'static', image_url)):
                        os.remove(os.path.join(app.root_path, 'static', image_url))
                    filename = secure_filename(file.filename)
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    filename = f"popup_{timestamp}_{filename}"
                    upload_folder = os.path.join(app.root_path, 'static', 'Uploads', 'popups')
                    if not os.path.exists(upload_folder):
                        os.makedirs(upload_folder, exist_ok=True)
                        os.chmod(upload_folder, 0o755)
                    file_path = os.path.join(upload_folder, filename)
                    file.save(file_path)
                    image_url = f"Uploads/popups/{filename}"
                    logging.debug(f"Popup image updated: {file_path}")

            cursor.execute('UPDATE popups SET title = %s, message = %s, image_url = %s, show_until = %s, type = %s WHERE id = %s',
                           (title, message, image_url, show_until, popup_type, id))
            conn.commit()
            flash('Popup updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating popup: {str(e)}', 'error')
            logging.error(f"Edit popup error: {str(e)}")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_popups'))
    try:
        cursor.execute('SELECT * FROM popups WHERE id = %s', (id,))
        popup = cursor.fetchone()
        if not popup:
            flash('Popup not found.', 'error')
            return redirect(url_for('admin_popups'))
        return render_template('edit_popup.html', popup=popup)
    except Exception as e:
        flash(f'Error fetching popup: {str(e)}', 'error')
        logging.error(f"Fetch popup error: {str(e)}")
        return redirect(url_for('admin_popups'))
    finally:
        cursor.close()
        conn.close()

@app.route('/delete_popup', methods=['POST'])
def delete_popup():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    try:
        id = request.form.get('id')
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT image_url FROM popups WHERE id = %s', (id,))
        popup = cursor.fetchone()
        if popup and popup['image_url'] and os.path.exists(os.path.join(app.root_path, 'static', popup['image_url'])):
            os.remove(os.path.join(app.root_path, 'static', popup['image_url']))
        cursor.execute('DELETE FROM popups WHERE id = %s', (id,))
        conn.commit()
        flash('Popup deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting popup: {str(e)}', 'error')
        logging.error(f"Delete popup error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_popups'))

@app.route('/get_popups')
def get_popups():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, title, message, image_url, type FROM popups WHERE show_until IS NULL OR show_until >= CURDATE()")
        popups = cursor.fetchall()
        return jsonify({'popups': popups})
    except Exception as e:
        logging.error(f"Get popups error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
        
@app.route('/admin_events')
def admin_events():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM events")
        events = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching events: {str(e)}', 'error')
        logging.error(f"Fetch events error: {str(e)}")
        events = []
    finally:
        cursor.close()
        conn.close()
    return render_template('admin_events.html', events=events)

@app.route('/add_event', methods=['POST'])
def add_event():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    try:
        title = request.form.get('title')
        date = request.form.get('date')
        description = request.form.get('description')
        if not all([title, date, description]):
            flash('All fields are required.', 'error')
            return redirect(url_for('admin_events'))
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER_EVENTS'], filename)
                file.save(file_path)
                image_url = f"Uploads/events/{filename}"
                logging.debug(f"Event image saved: {file_path}")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO events (title, date, description, image_url, created_at) VALUES (%s, %s, %s, %s, %s)',
            (title, date, description, image_url, datetime.utcnow()))
        conn.commit()
        flash('Event added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding event: {str(e)}', 'error')
        logging.error(f"Add event error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_events'))

@app.route('/edit_event/<int:id>', methods=['GET', 'POST'])
def edit_event(id):
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            date = request.form.get('date')
            description = request.form.get('description')
            if not all([title, date, description]):
                flash('All fields are required.', 'error')
                return redirect(url_for('admin_events'))
            image_url = request.form.get('existing_image_url')
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    if image_url and os.path.exists(os.path.join('static', image_url)):
                        os.remove(os.path.join('static', image_url))
                    filename = secure_filename(file.filename)
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER_EVENTS'], filename)
                    file.save(file_path)
                    image_url = f"Uploads/events/{filename}"
                    logging.debug(f"Event image updated: {file_path}")
            cursor.execute('UPDATE events SET title = %s, date = %s, description = %s, image_url = %s WHERE id = %s',
                           (title, date, description, image_url, id))
            conn.commit()
            flash('Event updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating event: {str(e)}', 'error')
            logging.error(f"Edit event error: {str(e)}")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_events'))
    try:
        cursor.execute('SELECT * FROM events WHERE id = %s', (id,))
        event = cursor.fetchone()
        if not event:
            flash('Event not found.', 'error')
            return redirect(url_for('admin_events'))
        return render_template('edit_event.html', event=event)
    except Exception as e:
        flash(f'Error fetching event: {str(e)}', 'error')
        logging.error(f"Fetch event error: {str(e)}")
        return redirect(url_for('admin_events'))
    finally:
        cursor.close()
        conn.close()

@app.route('/delete_event', methods=['POST'])
def delete_event():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    try:
        id = request.form.get('id')
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT image_url FROM events WHERE id = %s', (id,))
        event = cursor.fetchone()
        if event and event['image_url'] and os.path.exists(os.path.join('static', event['image_url'])):
            os.remove(os.path.join('static', event['image_url']))
        cursor.execute('DELETE FROM events WHERE id = %s', (id,))
        conn.commit()
        flash('Event deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting event: {str(e)}', 'error')
        logging.error(f"Delete event error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_events'))

@app.route('/admin_settings')
def admin_settings():
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM site_info")
        site_info = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching site info: {str(e)}', 'error')
        logging.error(f"Fetch site info error: {str(e)}")
        site_info = []
    finally:
        cursor.close()
        conn.close()
    return render_template('admin_settings.html', site_info=site_info)

@app.route('/submit_admission', methods=['POST'])
def submit_admission():
    try:
        # Retrieve form data with fallback to empty string or None
        student_name = request.form.get('studentName', '').strip()
        cnic = request.form.get('cnic', '').strip()
        dob = request.form.get('dob', '')
        gender = request.form.get('gender', '')
        age = request.form.get('age', '')  # Ensure fallback
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        student_occupation = request.form.get('studentOccupation', '').strip()
        parent_name = request.form.get('parentName', '').strip()
        parent_cnic = request.form.get('parentCnic', '').strip()
        parent_phone = request.form.get('parentPhone', '').strip()
        parent_occupation = request.form.get('parentOccupation', '').strip()
        num_siblings = request.form.get('numSiblings', '')
        sibling_disability = request.form.get('siblingDisability', '').strip()
        guardian_name = request.form.get('guardianName', '').strip()
        guardian_phone = request.form.get('guardianPhone', '').strip()
        disability_certificate = request.files.get('disabilityCertificate')
        disability_name = request.form.get('disabilityName', '')
        medical_history = request.form.get('medicalHistory', '').strip()
        regular_medication = request.form.get('regularMedication', '').strip()
        assistive_device = request.form.get('assistiveDevice', '').strip()
        epilepsy = request.form.get('epilepsy', '')
        drug_addiction = request.form.get('drugAddiction', '')
        assistant = request.form.get('assistant', '')
        communicable_disease = request.form.get('communicableDisease', '').strip()
        education_level = request.form.get('educationLevel', '').strip()
        documents = request.files.getlist('documents')
        course = request.form.get('course', '').strip()
        admission_type = request.form.get('admissionType', '').strip()
        duration_stay = request.form.get('durationStay', '')
        pick_drop = request.form.get('pickDrop', '').strip()
        affidavit = request.form.get('affidavit', '').strip()
        affidavit_agreement = request.form.get('affidavitAgreement', '')
        admission_date = request.form.get('admissionDate', '').strip()

        # Log form data for debugging
        form_data = {
            'student_name': student_name, 'cnic': cnic, 'dob': dob, 'gender': gender, 'age': age,
            'phone': phone, 'address': address, 'student_occupation': student_occupation,
            'parent_name': parent_name, 'parent_cnic': parent_cnic, 'parent_phone': parent_phone,
            'parent_occupation': parent_occupation, 'num_siblings': num_siblings,
            'sibling_disability': sibling_disability, 'guardian_name': guardian_name,
            'guardian_phone': guardian_phone, 'disability_name': disability_name,
            'medical_history': medical_history, 'regular_medication': regular_medication,
            'assistive_device': assistive_device, 'epilepsy': epilepsy,
            'drug_addiction': drug_addiction, 'assistant': assistant,
            'communicable_disease': communicable_disease, 'education_level': education_level,
            'course': course, 'admission_type': admission_type, 'duration_stay': duration_stay,
            'pick_drop': pick_drop, 'affidavit': affidavit, 'admission_date': admission_date,
            'affidavit_agreement': affidavit_agreement
        }
        logging.info(f"Received admission form data: {form_data}")

        # Validate required fields
        required_fields = {
            'Student Name': student_name, 'CNIC': cnic, 'Date of Birth': dob, 'Gender': gender,
            'Age': age, 'Phone': phone, 'Address': address, 'Parent Name': parent_name,
            'Parent CNIC': parent_cnic, 'Parent Phone': parent_phone, 'Parent Occupation': parent_occupation,
            'Number of Siblings': num_siblings, 'Guardian Name': guardian_name,
            'Guardian Phone': guardian_phone, 'Disability Name': disability_name,
            'Education Level': education_level, 'Documents': documents, 'Course': course,
            'Admission Type': admission_type, 'Affidavit': affidavit, 'Admission Date': admission_date
        }
        for field_name, value in required_fields.items():
            if not value and field_name not in ['Student Occupation', 'Sibling Disability', 'Disability Certificate',
                                               'Medical History', 'Regular Medication', 'Assistive Device',
                                               'Epilepsy', 'Drug Addiction', 'Assistant', 'Communicable Disease',
                                               'Duration Stay', 'Pick & Drop']:
                flash(f'{field_name} is required.', 'error')
                logging.error(f"Validation error: {field_name} is missing")
                return redirect(url_for('apply_now'))

        # Validate CNIC formats
        if not re.match(r'^\d{5}-\d{7}-\d{1}$', cnic):
            flash('Invalid Student CNIC format. Must be 12345-1234567-1.', 'error')
            logging.error(f"Validation error: Invalid Student CNIC format - Received: {cnic}")
            return redirect(url_for('apply_now'))
        if not re.match(r'^\d{5}-\d{7}-\d{1}$', parent_cnic):
            flash('Invalid Parent CNIC format. Must be 12345-1234567-1.', 'error')
            logging.error(f"Validation error: Invalid Parent CNIC format - Received: {parent_cnic}")
            return redirect(url_for('apply_now'))

        # Validate phone formats
        if not re.match(r'^\+92\d{10}$', phone):
            flash('Invalid Student Phone format. Must be +923123456789.', 'error')
            logging.error(f"Validation error: Invalid Student Phone format - Received: {phone}")
            return redirect(url_for('apply_now'))
        if not re.match(r'^\+92\d{10}$', parent_phone):
            flash('Invalid Parent Phone format. Must be +923123456789.', 'error')
            logging.error(f"Validation error: Invalid Parent Phone format - Received: {parent_phone}")
            return redirect(url_for('apply_now'))
        if not re.match(r'^\+92\d{10}$', guardian_phone):
            flash('Invalid Guardian Phone format. Must be +923123456789.', 'error')
            logging.error(f"Validation error: Invalid Guardian Phone format - Received: {guardian_phone}")
            return redirect(url_for('apply_now'))

        # Validate age
        try:
            age = int(age)
            if age < 1 or age > 120:
                flash('Age must be between 1 and 120.', 'error')
                logging.error(f"Validation error: Age out of range (1-120) - Received: {age}")
                return redirect(url_for('apply_now'))
        except ValueError:
            flash('Age must be a valid number between 1 and 120.', 'error')
            logging.error(f"Validation error: Age is not a number - Received: {age}")
            return redirect(url_for('apply_now'))

        # Validate dates
        try:
            dob_date = datetime.strptime(dob, '%Y-%m-%d')
            if dob_date > datetime.now():
                flash('Date of Birth cannot be in the future.', 'error')
                logging.error(f"Validation error: DOB in future - Received: {dob}")
                return redirect(url_for('apply_now'))
            admission_date_date = datetime.strptime(admission_date, '%Y-%m-%d')
            if admission_date_date > datetime.now():
                flash('Admission Date cannot be in the future.', 'error')
                logging.error(f"Validation error: Admission Date in future - Received: {admission_date}")
                return redirect(url_for('apply_now'))
        except ValueError:
            flash('Invalid Date of Birth or Admission Date format.', 'error')
            logging.error(f"Validation error: Invalid DOB or Admission Date format - Received: {dob}, {admission_date}")
            return redirect(url_for('apply_now'))

        # Validate gender
        if gender not in ['M', 'F']:
            flash('Invalid Gender selection.', 'error')
            logging.error(f"Validation error: Invalid Gender - Received: {gender}")
            return redirect(url_for('apply_now'))

        # Validate admission type
        if admission_type not in ['Day Scholar', 'Hostel Boarder']:
            flash('Invalid Admission Type selection.', 'error')
            logging.error(f"Validation error: Invalid Admission Type - Received: {admission_type}")
            return redirect(url_for('apply_now'))

        # Validate affidavit
        if affidavit not in ['Yes', 'No']:
            flash('Invalid Affidavit selection. Must be "Yes" or "No".', 'error')
            logging.error(f"Validation error: Invalid Affidavit - Received: {affidavit}")
            return redirect(url_for('apply_now'))
        if affidavit == 'Yes' and not affidavit_agreement:
            flash('You must agree to the affidavit terms.', 'error')
            logging.error("Validation error: Affidavit agreement not checked")
            return redirect(url_for('apply_now'))

        # Validate number of siblings
        try:
            num_siblings = int(num_siblings) if num_siblings else 0
            if num_siblings < 0:
                flash('Number of siblings cannot be negative.', 'error')
                logging.error(f"Validation error: Invalid number of siblings - Received: {num_siblings}")
                return redirect(url_for('apply_now'))
        except ValueError:
            flash('Number of siblings must be a valid number.', 'error')
            logging.error(f"Validation error: Number of siblings is not a number - Received: {num_siblings}")
            return redirect(url_for('apply_now'))

        # Validate duration stay
        try:
            duration_stay = int(duration_stay) if duration_stay else None
            if duration_stay is not None and duration_stay <= 0:
                flash('Duration of stay must be a positive number.', 'error')
                logging.error(f"Validation error: Invalid duration stay - Received: {duration_stay}")
                return redirect(url_for('apply_now'))
        except ValueError:
            flash('Duration of stay must be a valid number.', 'error')
            logging.error(f"Validation error: Duration stay is not a number - Received: {duration_stay}")
            return redirect(url_for('apply_now'))

        # Handle photo upload
        photo_path = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"photo_{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], filename)
                file.save(file_path)
                photo_path = f"Uploads/admissions/{filename}"
                logging.info(f"Photo saved: {file_path}")
            elif file.filename:
                flash(f'Invalid photo file type for {file.filename}. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}', 'error')
                logging.error(f"Invalid photo file type: {file.filename}")
                return redirect(url_for('apply_now'))

        # Handle disability certificate upload
        disability_certificate_path = None
        if disability_certificate and disability_certificate.filename:
            if allowed_file(disability_certificate.filename):
                filename = secure_filename(disability_certificate.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"disability_{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], filename)
                disability_certificate.save(file_path)
                disability_certificate_path = f"Uploads/admissions/{filename}"
                logging.info(f"Disability certificate saved: {file_path}")
            else:
                flash(f'Invalid disability certificate file type for {disability_certificate.filename}. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}', 'error')
                logging.error(f"Invalid disability certificate file type: {disability_certificate.filename}")
                return redirect(url_for('apply_now'))

        # Handle documents upload
        document_paths = []
        if not any(file.filename for file in documents):
            flash('At least one degree certificate is required.', 'error')
            logging.error("Validation error: No documents uploaded")
            return redirect(url_for('apply_now'))
        for file in documents:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"document_{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], filename)
                file.save(file_path)
                document_paths.append(f"Uploads/admissions/{filename}")
                logging.info(f"Document saved: {file_path}")
            else:
                flash(f'Invalid file type for {file.filename}. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}', 'error')
                logging.error(f"Invalid file type: {file.filename}")
                return redirect(url_for('apply_now'))
        documents_str = ','.join(document_paths) if document_paths else None

        # Insert into database with all parameters
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO admissions (student_name, cnic, dob, gender, age, phone, address, student_occupation,
               parent_name, parent_cnic, parent_phone, parent_occupation, num_siblings, sibling_disability,
               guardian_name, guardian_phone, disability_certificate, disability_name, medical_history,
               regular_medication, assistive_device, epilepsy, drug_addiction, assistant, communicable_disease,
               education_level, documents, course, admission_type, duration_stay, pick_drop, affidavit,
               admission_date, photo)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (student_name, cnic, dob, gender, age, phone, address, student_occupation,
             parent_name, parent_cnic, parent_phone, parent_occupation, num_siblings, sibling_disability,
             guardian_name, guardian_phone, disability_certificate_path, disability_name, medical_history,
             regular_medication, assistive_device, epilepsy, drug_addiction, assistant, communicable_disease,
             education_level, documents_str, course, admission_type, duration_stay, pick_drop, affidavit,
             admission_date, photo_path)
        )
        conn.commit()
        flash('Admission application submitted successfully!', 'success')
        logging.info(f"Admission submitted successfully: {form_data}, Documents: {documents_str}, Photo: {photo_path}, Disability Certificate: {disability_certificate_path}")
        return jsonify({'redirect': url_for('apply_now')})
    except Exception as e:
        flash(f'Error submitting admission: {str(e)}', 'error')
        logging.error(f"Submit admission error: {str(e)} with form data: {form_data}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
    return jsonify({'error': 'Submission failed. Please try again.'})

@app.route('/admin_admissions')
def admin_admissions():
    if session.get('user_type') != 'admin':
        logging.warning(f"Unauthorized access attempt to /admin_admissions, user_type: {session.get('user_type')}")
        flash('Please log in as an admin.', 'danger')
        return redirect(url_for('guardian'))
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        logging.debug("Executing query for all admissions")
        cursor.execute("""
            SELECT id, student_name, cnic, dob, gender, age, phone, address, student_occupation,
                   parent_name, parent_cnic, parent_phone, parent_occupation, num_siblings, sibling_disability,
                   guardian_name, guardian_phone, disability_certificate, disability_name, medical_history,
                   regular_medication, assistive_device, epilepsy, drug_addiction, assistant, communicable_disease,
                   education_level, documents, course, admission_type, duration_stay, pick_drop, affidavit,
                   admission_date, photo, created_at
            FROM admissions
            ORDER BY created_at DESC
        """)
        admissions = cursor.fetchall()  # Fetch once
        if not admissions:
            admissions = []
        for admission in admissions:
            admission['dob'] = admission['dob'].strftime('%Y-%m-%d') if admission['dob'] else 'N/A'
            admission['admission_date'] = admission['admission_date'].strftime('%Y-%m-%d') if admission['admission_date'] else 'N/A'
            admission['created_at'] = admission['created_at'].strftime('%Y-%m-%d %H:%M:%S') if admission['created_at'] else 'N/A'
            admission['documents'] = admission['documents'].split(',') if admission['documents'] else []
            for key in admission:
                if admission[key] is None:
                    admission[key] = 'N/A'
        logging.info(f"Fetched {len(admissions)} admissions: {admissions[:1]}...")  # Log first record for debug
        return render_template('admin_admissions.html', admissions=admissions)
    except mysql.connector.Error as db_error:
        logging.error(f"Database error in admin_admissions: {str(db_error)}")
        flash(f"Database error: {str(db_error)}", 'error')
        return render_template('admin_admissions.html', admissions=[])
    except Exception as e:
        logging.error(f"Unexpected error in admin_admissions: {str(e)}")
        flash(f"Server error: {str(e)}", 'error')
        return render_template('admin_admissions.html', admissions=[])
    finally:
        cursor.close()
        conn.close()

@app.route('/view_admission/<int:id>')
def view_admission(id):
    if session.get('user_type') != 'admin':
        flash('Please log in as an admin.', 'error')
        return redirect(url_for('guardian_login_page'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM admissions WHERE id = %s", (id,))
        admission = cursor.fetchone()
        if not admission:
            flash('Admission record not found.', 'error')
            return redirect(url_for('admin_admissions'))
        logging.debug(f"Fetched admission: {admission}")
    except Exception as e:
        flash(f'Error fetching admission details: {str(e)}', 'error')
        logging.error(f"View admission error: {str(e)}")
        admission = None
    finally:
        cursor.close()
        conn.close()
    return render_template('view_admission.html', admission=admission)

@app.route('/api/admission/delete', methods=['POST'])
def delete_admissions():
    if session.get('user_type') != 'admin':
        logging.warning(f"Unauthorized access attempt to /api/admission/delete, user_type: {session.get('user_type')}")
        return jsonify({'success': False, 'error': 'Please log in as an admin.'}), 401
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        if not ids:
            logging.error("No admission IDs provided for deletion")
            return jsonify({'success': False, 'error': 'No admissions selected'}), 400

        conn = get_connection()
        if not conn.is_connected():
            logging.error("Database connection failed")
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        cursor = conn.cursor(dictionary=True)

        # Fetch file paths for deletion
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(f"""
            SELECT id, photo, disability_certificate, documents
            FROM admissions
            WHERE id IN ({placeholders})
        """, ids)
        admissions = cursor.fetchall()

        # Delete associated files
        for admission in admissions:
            # Delete photo
            if admission['photo'] and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], os.path.relpath(admission['photo'], 'Uploads/admissions'))):
                os.remove(os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], os.path.relpath(admission['photo'], 'Uploads/admissions')))
                logging.info(f"Deleted photo: {admission['photo']} for admission ID {admission['id']}")
            # Delete disability certificate
            if admission['disability_certificate'] and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], os.path.relpath(admission['disability_certificate'], 'Uploads/admissions'))):
                os.remove(os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], os.path.relpath(admission['disability_certificate'], 'Uploads/admissions')))
                logging.info(f"Deleted disability certificate: {admission['disability_certificate']} for admission ID {admission['id']}")
            # Delete documents
            if admission['documents']:
                for doc in admission['documents'].split(','):
                    if doc and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], os.path.relpath(doc, 'Uploads/admissions'))):
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER_ADMISSIONS'], os.path.relpath(doc, 'Uploads/admissions')))
                        logging.info(f"Deleted document: {doc} for admission ID {admission['id']}")

        # Delete admissions from database
        cursor.execute(f"DELETE FROM admissions WHERE id IN ({placeholders})", ids)
        if cursor.rowcount == 0:
            logging.warning(f"No admissions found for IDs: {ids}")
            conn.rollback()
            return jsonify({'success': False, 'error': 'No admissions found for the provided IDs'}), 404

        conn.commit()
        logging.info(f"Successfully deleted {cursor.rowcount} admissions with IDs: {ids}")
        return jsonify({'success': True, 'message': f'Deleted {cursor.rowcount} admissions successfully'})
    except mysql.connector.Error as db_error:
        logging.error(f"Database error in delete_admissions: {str(db_error)}", exc_info=True)
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'success': False, 'error': f'Database error: {str(db_error)}'}), 500
    except Exception as e:
        logging.error(f"Unexpected error in delete_admissions: {str(e)}", exc_info=True)
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=False)