import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    from flask_mail import Mail, Message
except ImportError:  # pragma: no cover
    Mail = None
    Message = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'smartcare.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
SPECIALIZATIONS = [
    'Cardiologist',
    'Dermatologist',
    'Neurologist',
    'Pediatrician',
    'Dentist',
    'Orthopedic',
    'General Physician',
    'Gynecologist',
    'Ophthalmologist',
]

app = Flask(__name__)
app.config['SECRET_KEY'] = 'smartcare-secret-key-2026'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MAIL_SERVER'] = 'localhost'
app.config['MAIL_PORT'] = 25
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEFAULT_SENDER'] = 'no-reply@smartcare.local'

if Mail is not None:
    mail = Mail(app)
else:
    mail = None

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    if 'db' not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_code TEXT UNIQUE,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            dob TEXT,
            gender TEXT,
            address TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient','doctor','admin')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    db.execute(
        '''
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            doctor_code TEXT UNIQUE,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            specialization TEXT NOT NULL,
            qualification TEXT,
            experience_years INTEGER,
            consultation_fee REAL,
            clinic_name TEXT,
            available_days TEXT,
            time_slots TEXT,
            bio TEXT,
            photo_url TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        '''
    )
    db.execute(
        '''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_code TEXT UNIQUE,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Approved','Rejected','Cancelled','Completed')),
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(doctor_id) REFERENCES doctors(id)
        )
        '''
    )
    db.execute(
        '''
        CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES users(id)
        )
        '''
    )
    db.execute(
        '''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        '''
    )
    db.commit()


def seed_data():
    db = get_db()
    admin_email = 'admin@smartcare.com'
    admin = db.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
    if admin is None:
        db.execute(
            'INSERT INTO users (user_code, full_name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?, ?)',
            ('ADM-1001', 'SmartCare Admin', admin_email, '+0000000000', generate_password_hash('Admin@123'), 'admin')
        )
        db.commit()

    doctor_count = db.execute('SELECT COUNT(*) AS count FROM doctors').fetchone()['count']
    if doctor_count == 0:
        doctors = [
            {
                'user_code': 'DOC-1001',
                'full_name': 'Dr. Maya Patel',
                'email': 'maya.patel@smartcare.com',
                'specialization': 'Cardiologist',
                'qualification': 'MD, DM Cardiology',
                'experience_years': 12,
                'consultation_fee': 1500,
                'clinic_name': 'CarePoint Heart Center',
                'available_days': ['Mon', 'Tue', 'Wed', 'Fri'],
                'time_slots': ['09:00 AM', '11:00 AM', '02:00 PM'],
                'bio': 'Expert in preventive cardiology and advanced heart care.',
                'photo_url': 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&w=800&q=80',
            },
            {
                'user_code': 'DOC-1002',
                'full_name': 'Dr. Aisha Khan',
                'email': 'aisha.khan@smartcare.com',
                'specialization': 'Dermatologist',
                'qualification': 'MBBS, MD Dermatology',
                'experience_years': 9,
                'consultation_fee': 1200,
                'clinic_name': 'GlowSkin Clinic',
                'available_days': ['Tue', 'Thu', 'Sat'],
                'time_slots': ['10:00 AM', '01:00 PM', '04:00 PM'],
                'bio': 'Treats acne, pigmentation, skin allergies, and aesthetic concerns.',
                'photo_url': 'https://images.unsplash.com/photo-1594824476967-48c8b964273f?auto=format&fit=crop&w=800&q=80',
            },
            {
                'user_code': 'DOC-1003',
                'full_name': 'Dr. Ravi Sharma',
                'email': 'ravi.sharma@smartcare.com',
                'specialization': 'Neurologist',
                'qualification': 'MBBS, DM Neurology',
                'experience_years': 15,
                'consultation_fee': 1800,
                'clinic_name': 'NeuroLife Clinic',
                'available_days': ['Mon', 'Wed', 'Thu', 'Sat'],
                'time_slots': ['08:30 AM', '12:00 PM', '03:30 PM'],
                'bio': 'Specialized in headache disorders, stroke care, and neuro rehabilitation.',
                'photo_url': 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=800&q=80',
            },
        ]
        for doctor in doctors:
            user = db.execute('SELECT id FROM users WHERE email = ?', (doctor['email'],)).fetchone()
            if user is None:
                user_id = db.execute(
                    'INSERT INTO users (user_code, full_name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?, ?)',
                    (doctor['user_code'], doctor['full_name'], doctor['email'], '+919876543210', generate_password_hash('Doctor@123'), 'doctor')
                ).lastrowid
            else:
                user_id = user['id']
            db.execute(
                '''
                INSERT INTO doctors (user_id, doctor_code, full_name, email, specialization, qualification, experience_years,
                consultation_fee, clinic_name, available_days, time_slots, bio, photo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    user_id,
                    doctor['user_code'],
                    doctor['full_name'],
                    doctor['email'],
                    doctor['specialization'],
                    doctor['qualification'],
                    doctor['experience_years'],
                    doctor['consultation_fee'],
                    doctor['clinic_name'],
                    json.dumps(doctor['available_days']),
                    json.dumps(doctor['time_slots']),
                    doctor['bio'],
                    doctor['photo_url'],
                )
            )
        db.commit()

    sample_patient = db.execute('SELECT id FROM users WHERE email = ?', ('patient@smartcare.com',)).fetchone()
    if sample_patient is None:
        db.execute(
            'INSERT INTO users (user_code, full_name, email, phone, dob, gender, address, password_hash, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            ('PAT-1001', 'Alicia Johnson', 'patient@smartcare.com', '+919999999999', '1994-06-14', 'Female', '12 Green Avenue, Hyderabad', generate_password_hash('Patient@123'), 'patient')
        )
        db.commit()

    sample_record = db.execute('SELECT id FROM medical_records WHERE patient_id = ?', (db.execute('SELECT id FROM users WHERE email = ?', ('patient@smartcare.com',)).fetchone()['id'],)).fetchone()
    if sample_record is None:
        patient_id = db.execute('SELECT id FROM users WHERE email = ?', ('patient@smartcare.com',)).fetchone()['id']
        db.execute(
            'INSERT INTO medical_records (patient_id, title, details) VALUES (?, ?, ?)',
            (patient_id, 'Annual Checkup', 'Blood pressure normal, vitamin D slight deficiency noted. Follow-up in 3 months.')
        )
        db.commit()


def ensure_user_record(user_id):
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def get_user_by_email(email):
    db = get_db()
    return db.execute('SELECT * FROM users WHERE email = ?', (email.lower().strip(),)).fetchone()


def get_patient_by_user_id(user_id):
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id = ? AND role = ?', (user_id, 'patient')).fetchone()


def get_doctor_by_user_id(user_id):
    db = get_db()
    return db.execute('SELECT * FROM doctors WHERE user_id = ?', (user_id,)).fetchone()


def get_doctor_by_id(doctor_id):
    db = get_db()
    return db.execute('SELECT * FROM doctors WHERE id = ?', (doctor_id,)).fetchone()


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return ensure_user_record(user_id)


@app.before_request
def load_user():
    g.user = get_current_user()


@app.context_processor
def inject_globals():
    return {'current_user': g.user, 'specializations': SPECIALIZATIONS}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user or g.user['role'] not in allowed_roles:
                flash('You are not authorized to access this page.', 'danger')
                return redirect(url_for('index'))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def parse_json_list(value):
    try:
        return json.loads(value) if value else []
    except (TypeError, ValueError):
        return []


def is_password_strong(password):
    return len(password) >= 8 and re.search(r'[A-Z]', password) and re.search(r'[a-z]', password) and re.search(r'\d', password)


def save_upload(file):
    if not file or file.filename == '':
        return ''
    filename = secure_filename(file.filename)
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return ''
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(file_path)
    return url_for('static', filename=f'uploads/{unique_name}')


@app.route('/')
def index():
    db = get_db()
    doctors = db.execute('SELECT * FROM doctors WHERE is_active = 1 ORDER BY id DESC LIMIT 3').fetchall()
    return render_template('index.html', doctors=doctors)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        dob = request.form.get('dob', '')
        gender = request.form.get('gender', '')
        address = request.form.get('address', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not full_name or not email or not phone or not dob or not gender or not password:
            flash('Please complete all required fields.', 'danger')
            return render_template('register.html')

        if '@' not in email or '.' not in email:
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')

        if get_user_by_email(email):
            flash('This email is already registered. Please log in instead.', 'danger')
            return render_template('register.html')

        if not is_password_strong(password):
            flash('Password must be at least 8 characters and include uppercase, lowercase, and a number.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')

        db = get_db()
        cursor = db.execute(
            'INSERT INTO users (user_code, full_name, email, phone, dob, gender, address, password_hash, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                'PAT-' + str(datetime.now().strftime('%Y%m%d%H%M%S')),
                full_name,
                email,
                phone,
                dob,
                gender,
                address,
                generate_password_hash(password),
                'patient',
            )
        )
        db.commit()
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = get_user_by_email(email)

        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash('Welcome back!', 'success')
            if user['role'] == 'patient':
                return redirect(url_for('patient_dashboard'))
            if user['role'] == 'doctor':
                return redirect(url_for('doctor_dashboard'))
            return redirect(url_for('admin_dashboard'))

        flash('Invalid email or password. Please try again.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = get_user_by_email(email)
        if user:
            flash(f'A password reset link has been sent to {email}.', 'success')
        else:
            flash('No account was found for that email address.', 'warning')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/patient/dashboard')
@login_required
@role_required('patient')
def patient_dashboard():
    db = get_db()
    patient_id = g.user['id']
    appointments = db.execute(
        '''
        SELECT a.*, d.full_name AS doctor_name, d.specialization, d.photo_url
        FROM appointments a
        JOIN doctors d ON d.id = a.doctor_id
        WHERE a.patient_id = ?
        ORDER BY a.appointment_date DESC, a.time_slot DESC
        ''',
        (patient_id,)
    ).fetchall()
    records = db.execute('SELECT * FROM medical_records WHERE patient_id = ? ORDER BY created_at DESC', (patient_id,)).fetchall()
    notifications = db.execute('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5', (patient_id,)).fetchall()

    counts = {
        'upcoming': sum(1 for appt in appointments if appt['status'] in ('Pending', 'Approved')),
        'pending': sum(1 for appt in appointments if appt['status'] == 'Pending'),
        'approved': sum(1 for appt in appointments if appt['status'] == 'Approved'),
        'cancelled': sum(1 for appt in appointments if appt['status'] == 'Cancelled'),
        'completed': sum(1 for appt in appointments if appt['status'] == 'Completed'),
    }

    return render_template('dashboard.html', appointments=appointments, records=records, notifications=notifications, counts=counts)


@app.route('/doctors')
def doctor_directory():
    db = get_db()
    q = request.args.get('q', '').strip()
    specialization = request.args.get('specialization', '').strip()

    query = 'SELECT * FROM doctors WHERE is_active = 1'
    params = []
    if q:
        query += ' AND (full_name LIKE ? OR specialization LIKE ? OR clinic_name LIKE ?)' 
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%'])
    if specialization:
        query += ' AND specialization = ?'
        params.append(specialization)
    query += ' ORDER BY full_name ASC'

    doctors = db.execute(query, params).fetchall()
    return render_template('doctor_directory.html', doctors=doctors, q=q, specialization=specialization)


@app.route('/doctor/<int:doctor_id>')
def doctor_profile(doctor_id):
    doctor = get_doctor_by_id(doctor_id)
    if not doctor:
        flash('Doctor not found.', 'warning')
        return redirect(url_for('doctor_directory'))
    return render_template('doctor_profile.html', doctor=doctor)


@app.route('/book/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
@role_required('patient')
def book_appointment(doctor_id):
    doctor = get_doctor_by_id(doctor_id)
    if not doctor or doctor['is_active'] != 1:
        flash('This doctor is unavailable right now.', 'warning')
        return redirect(url_for('doctor_directory'))

    if request.method == 'POST':
        appointment_date = request.form.get('appointment_date', '').strip()
        time_slot = request.form.get('time_slot', '').strip()
        reason = request.form.get('reason', '').strip()

        if not appointment_date or not time_slot or not reason:
            flash('Please complete date, time slot, and consultation reason.', 'danger')
            return render_template('appointment_booking.html', doctor=doctor)

        selected_date = datetime.strptime(appointment_date, '%Y-%m-%d').date()
        today = datetime.now().date()
        if selected_date < today:
            flash('You cannot book appointments in the past.', 'danger')
            return render_template('appointment_booking.html', doctor=doctor)

        available_days = parse_json_list(doctor['available_days'])
        available_slots = parse_json_list(doctor['time_slots'])
        if selected_date.strftime('%a') not in available_days:
            flash('This doctor is not available on the selected day.', 'danger')
            return render_template('appointment_booking.html', doctor=doctor)
        if time_slot not in available_slots:
            flash('Please select an available slot.', 'danger')
            return render_template('appointment_booking.html', doctor=doctor)

        db = get_db()
        existing = db.execute(
            '''
            SELECT id FROM appointments
            WHERE doctor_id = ? AND appointment_date = ? AND time_slot = ? AND status NOT IN ('Cancelled','Rejected')
            ''',
            (doctor_id, appointment_date, time_slot)
        ).fetchone()
        if existing:
            flash('This time slot is already booked. Please choose another one.', 'danger')
            return render_template('appointment_booking.html', doctor=doctor)

        appointment_code = f"APT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        db.execute(
            'INSERT INTO appointments (appointment_code, patient_id, doctor_id, appointment_date, time_slot, reason, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (appointment_code, g.user['id'], doctor_id, appointment_date, time_slot, reason, 'Pending')
        )
        db.execute(
            'INSERT INTO notifications (user_id, message) VALUES (?, ?)',
            (g.user['id'], f'Your appointment with {doctor["full_name"]} is pending approval.')
        )
        db.commit()
        flash('Appointment booked successfully. Please wait for doctor approval.', 'success')
        return redirect(url_for('patient_dashboard'))

    return render_template('appointment_booking.html', doctor=doctor)


@app.route('/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
@role_required('patient')
def cancel_appointment(appt_id):
    db = get_db()
    appointment = db.execute('SELECT * FROM appointments WHERE id = ? AND patient_id = ?', (appt_id, g.user['id'])).fetchone()
    if not appointment:
        flash('Appointment not found.', 'warning')
        return redirect(url_for('patient_dashboard'))
    if appointment['status'] in ('Cancelled', 'Completed'):
        flash('This appointment cannot be cancelled.', 'warning')
        return redirect(url_for('patient_dashboard'))
    db.execute('UPDATE appointments SET status = ? WHERE id = ?', ('Cancelled', appt_id))
    db.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (g.user['id'], f'Your appointment {appointment["appointment_code"]} has been cancelled.'))
    db.commit()
    flash('Appointment cancelled successfully.', 'info')
    return redirect(url_for('patient_dashboard'))


@app.route('/appointments/<int:appt_id>/reschedule', methods=['GET', 'POST'])
@login_required
@role_required('patient')
def reschedule_appointment(appt_id):
    db = get_db()
    appointment = db.execute(
        '''
        SELECT a.*, d.full_name, d.available_days, d.time_slots
        FROM appointments a
        JOIN doctors d ON d.id = a.doctor_id
        WHERE a.id = ? AND a.patient_id = ?
        ''',
        (appt_id, g.user['id'])
    ).fetchone()
    if not appointment:
        flash('Appointment not found.', 'warning')
        return redirect(url_for('patient_dashboard'))

    doctor = get_doctor_by_id(appointment['doctor_id'])
    if request.method == 'POST':
        date_value = request.form.get('appointment_date', '').strip()
        slot_value = request.form.get('time_slot', '').strip()
        if not date_value or not slot_value:
            flash('Please select a new date and time slot.', 'danger')
            return render_template('reschedule_appointment.html', appointment=appointment, doctor=doctor)

        selected_date = datetime.strptime(date_value, '%Y-%m-%d').date()
        if selected_date < datetime.now().date():
            flash('You cannot reschedule to a past date.', 'danger')
            return render_template('reschedule_appointment.html', appointment=appointment, doctor=doctor)

        available_days = parse_json_list(doctor['available_days'])
        available_slots = parse_json_list(doctor['time_slots'])
        if selected_date.strftime('%a') not in available_days or slot_value not in available_slots:
            flash('Selected date or time slot is unavailable.', 'danger')
            return render_template('reschedule_appointment.html', appointment=appointment, doctor=doctor)

        conflict = db.execute(
            'SELECT id FROM appointments WHERE doctor_id = ? AND appointment_date = ? AND time_slot = ? AND id != ? AND status NOT IN (?, ?)',
            (doctor['id'], date_value, slot_value, appt_id, 'Cancelled', 'Rejected')
        ).fetchone()
        if conflict:
            flash('That time slot is already booked. Please choose another one.', 'danger')
            return render_template('reschedule_appointment.html', appointment=appointment, doctor=doctor)

        db.execute(
            'UPDATE appointments SET appointment_date = ?, time_slot = ?, status = ? WHERE id = ?',
            (date_value, slot_value, 'Pending', appt_id)
        )
        db.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (g.user['id'], f'Your appointment has been rescheduled to {date_value} at {slot_value}.'))
        db.commit()
        flash('Appointment rescheduled successfully. Awaiting doctor approval.', 'success')
        return redirect(url_for('patient_dashboard'))

    return render_template('reschedule_appointment.html', appointment=appointment, doctor=doctor)


@app.route('/appointments/<int:appt_id>/receipt')
@login_required
def appointment_receipt(appt_id):
    db = get_db()
    appointment = db.execute(
        '''
        SELECT a.*, p.full_name AS patient_name, d.full_name AS doctor_name, d.specialization, d.clinic_name
        FROM appointments a
        JOIN users p ON p.id = a.patient_id
        JOIN doctors d ON d.id = a.doctor_id
        WHERE a.id = ?
        ''',
        (appt_id,)
    ).fetchone()
    if not appointment:
        flash('Receipt not found.', 'warning')
        return redirect(url_for('patient_dashboard'))
    if g.user['role'] not in ('patient', 'doctor', 'admin'):
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    if g.user['role'] == 'patient' and appointment['patient_id'] != g.user['id']:
        flash('This receipt is not available to you.', 'danger')
        return redirect(url_for('patient_dashboard'))
    return render_template('receipt.html', appointment=appointment)


@app.route('/doctor/dashboard')
@login_required
@role_required('doctor')
def doctor_dashboard():
    doctor = get_doctor_by_user_id(g.user['id'])
    if not doctor:
        flash('Doctor profile not found. Please contact admin.', 'warning')
        return redirect(url_for('logout'))

    db = get_db()
    appointments = db.execute(
        '''
        SELECT a.*, p.full_name AS patient_name, p.phone, p.gender
        FROM appointments a
        JOIN users p ON p.id = a.patient_id
        WHERE a.doctor_id = ?
        ORDER BY a.appointment_date DESC, a.time_slot DESC
        ''',
        (doctor['id'],)
    ).fetchall()
    return render_template('doctor_dashboard.html', doctor=doctor, appointments=appointments)


@app.route('/doctor/appointment/<int:appt_id>/update', methods=['POST'])
@login_required
@role_required('doctor')
def update_doctor_appointment(appt_id):
    db = get_db()
    doctor = get_doctor_by_user_id(g.user['id'])
    appointment = db.execute('SELECT * FROM appointments WHERE id = ? AND doctor_id = ?', (appt_id, doctor['id'])).fetchone()
    if not appointment:
        flash('Appointment not found or unauthorized.', 'warning')
        return redirect(url_for('doctor_dashboard'))

    action = request.form.get('action', 'approve')
    if action == 'approve':
        status = 'Approved'
    elif action == 'reject':
        status = 'Rejected'
    elif action == 'complete':
        status = 'Completed'
    else:
        status = appointment['status']

    db.execute('UPDATE appointments SET status = ? WHERE id = ?', (status, appt_id))
    db.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (appointment['patient_id'], f'Your appointment {appointment["appointment_code"]} is now marked as {status}.'))
    db.commit()
    flash(f'Appointment status updated to {status}.', 'success')
    return redirect(url_for('doctor_dashboard'))


@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    db = get_db()
    patient_count = db.execute('SELECT COUNT(*) AS count FROM users WHERE role = ?', ('patient',)).fetchone()['count']
    doctor_count = db.execute('SELECT COUNT(*) AS count FROM doctors WHERE is_active = 1').fetchone()['count']
    appointments = db.execute('SELECT * FROM appointments ORDER BY created_at DESC').fetchall()
    doctors = db.execute('SELECT * FROM doctors ORDER BY full_name ASC').fetchall()

    counts = {
        'total_appointments': len(appointments),
        'pending': sum(1 for appt in appointments if appt['status'] == 'Pending'),
        'approved': sum(1 for appt in appointments if appt['status'] == 'Approved'),
        'completed': sum(1 for appt in appointments if appt['status'] == 'Completed'),
        'cancelled': sum(1 for appt in appointments if appt['status'] == 'Cancelled'),
    }
    return render_template('admin_dashboard.html', patient_count=patient_count, doctor_count=doctor_count, appointments=appointments, doctors=doctors, counts=counts)


@app.route('/admin/doctors/add', methods=['POST'])
@login_required
@role_required('admin')
def add_doctor():
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    specialization = request.form.get('specialization', '').strip()
    qualification = request.form.get('qualification', '').strip()
    experience_years = request.form.get('experience_years', '0')
    consultation_fee = request.form.get('consultation_fee', '0')
    clinic_name = request.form.get('clinic_name', '').strip()
    available_days = request.form.getlist('available_days')
    time_slots = request.form.getlist('time_slots')
    bio = request.form.get('bio', '').strip()
    photo = request.files.get('photo')

    if not full_name or not email or not specialization or not clinic_name:
        flash('Please complete the required doctor details.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if get_user_by_email(email):
        flash('A user with this email already exists.', 'danger')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    photo_url = save_upload(photo) or 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&w=800&q=80'
    user_id = db.execute(
        'INSERT INTO users (user_code, full_name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?, ?)',
        (f"DOC-{datetime.now().strftime('%Y%m%d%H%M%S')}", full_name, email, '+919900000000', generate_password_hash('Doctor@123'), 'doctor')
    ).lastrowid
    db.execute(
        '''
        INSERT INTO doctors (user_id, doctor_code, full_name, email, specialization, qualification, experience_years,
        consultation_fee, clinic_name, available_days, time_slots, bio, photo_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            user_id,
            f"DOC-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            full_name,
            email,
            specialization,
            qualification,
            int(experience_years),
            float(consultation_fee),
            clinic_name,
            json.dumps(available_days),
            json.dumps(time_slots),
            bio,
            photo_url,
        )
    )
    db.commit()
    flash('Doctor profile added successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/doctor/<int:doctor_id>/toggle', methods=['POST'])
@login_required
@role_required('admin')
def toggle_doctor(doctor_id):
    db = get_db()
    doctor = get_doctor_by_id(doctor_id)
    if not doctor:
        flash('Doctor not found.', 'warning')
        return redirect(url_for('admin_dashboard'))
    new_state = 0 if doctor['is_active'] == 1 else 1
    db.execute('UPDATE doctors SET is_active = ? WHERE id = ?', (new_state, doctor_id))
    db.commit()
    flash(f'Doctor status updated to {"Active" if new_state else "Inactive"}.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/health-library')
def health_library():
    articles = [
        {'title': 'Healthy Habits for Better Sleep', 'summary': 'Practical steps to improve sleep quality and reduce fatigue.'},
        {'title': 'Nutrition Tips for Heart Health', 'summary': 'Simple diet changes that help maintain healthy blood pressure and circulation.'},
        {'title': 'Managing Stress Naturally', 'summary': 'Mental wellness strategies to reduce stress and stay productive.'},
    ]
    return render_template('health_library.html', articles=articles)


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        flash('Thank you for contacting SmartCare. Our team will get back to you soon.', 'success')
        return redirect(url_for('index'))
    return render_template('contact.html')


@app.route('/services')
def services():
    return render_template('services.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('patient')
def patient_profile():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        dob = request.form.get('dob', '').strip()
        gender = request.form.get('gender', '').strip()
        address = request.form.get('address', '').strip()

        if not full_name or not phone:
            flash('Please enter your name and phone number.', 'danger')
            return redirect(url_for('patient_profile'))

        db = get_db()
        db.execute(
            'UPDATE users SET full_name = ?, phone = ?, dob = ?, gender = ?, address = ? WHERE id = ?',
            (full_name, phone, dob, gender, address, g.user['id'])
        )
        db.commit()
        flash('Your profile has been updated successfully.', 'success')
        return redirect(url_for('patient_profile'))

    user = g.user
    return render_template('profile.html', user=user)


@app.route('/admin/create-system')
def create_system():
    init_db()
    seed_data()
    flash('System initialized successfully.', 'success')
    return redirect(url_for('index'))


@app.route('/health')
def health_check():
    return {'status': 'ok', 'app': 'SmartCare'}, 200


with app.app_context():
    init_db()
    seed_data()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
