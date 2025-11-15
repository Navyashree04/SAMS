from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date, time
import io
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import csv
from io import StringIO, BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import random

import os

app = Flask(__name__)
# Load secret key from environment for stability across restarts. If not provided, fall back to an ephemeral key (development only).
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
if 'SECRET_KEY' not in os.environ:
    app.logger.warning('Using ephemeral SECRET_KEY; set the SECRET_KEY environment variable for production to persist sessions and improve security.')
# Allow DATABASE_URL env var (useful for production). Defaults to local sqlite file.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///sams.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # 30-minute timeout

db = SQLAlchemy(app)

# ==================== SESSION TIMEOUT HANDLER ====================

@app.before_request
def check_session_timeout():
    """Enforce 30-minute session timeout"""
    if 'user_id' in session:
        session.permanent = True
        last_activity = session.get('last_activity')
        
        if last_activity:
            # Check if more than 30 minutes have passed
            last_activity_time = datetime.fromisoformat(last_activity)
            if datetime.now() - last_activity_time > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('login'))
        
        # Update last activity time
        session['last_activity'] = datetime.now().isoformat()

# ==================== DATABASE MODELS ====================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    department = db.Column(db.String(100))
    year = db.Column(db.Integer)
    section = db.Column(db.String(10))
    parent_email = db.Column(db.String(120))
    parent_phone = db.Column(db.String(20))
    user = db.relationship('User', backref='student_profile')

class Faculty(db.Model):
    __tablename__ = 'faculty'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    faculty_id = db.Column(db.String(20), unique=True, nullable=False)
    department = db.Column(db.String(100))
    designation = db.Column(db.String(50))
    user = db.relationship('User', backref='faculty_profile')

class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), unique=True, nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    credits = db.Column(db.Integer)
    year = db.Column(db.Integer)
    semester = db.Column(db.Integer)

class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    section = db.Column(db.String(10))
    schedule = db.Column(db.String(100))
    room = db.Column(db.String(20))
    course = db.relationship('Course', backref='classes')
    faculty = db.relationship('Faculty', backref='classes')

class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    enrollment_date = db.Column(db.DateTime, default=datetime.utcnow)
    student = db.relationship('Student', backref='enrollments')
    class_ref = db.relationship('Class', backref='enrollments')

class AttendanceSession(db.Model):
    __tablename__ = 'attendance_sessions'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    class_ref = db.relationship('Class', backref='attendance_sessions')

class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)
    marked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    method = db.Column(db.String(20))
    session = db.relationship('AttendanceSession', backref='attendance_records')
    student = db.relationship('Student', backref='attendance_records')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='notifications')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== HELPER FUNCTIONS ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            user = User.query.get(session['user_id'])
            # If user record was removed or is missing, clear session and force re-login
            if not user:
                session.clear()
                flash('Your session is invalid. Please log in again.', 'warning')
                return redirect(url_for('login'))

            if user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_audit(action, entity_type=None, entity_id=None, details=None):
    try:
        log = AuditLog(
            user_id=session.get('user_id'),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        # Do not silently ignore audit logging failures — record to application logger for investigation.
        app.logger.exception('Failed to write audit log: %s', e)

def send_email(to_email, subject, body):
    """Send an email using SMTP credentials from environment.

    Required environment variables (recommended): SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
    Returns True on success, False on failure.
    """
    try:
        SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
        SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
        SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')

        if not SMTP_USERNAME or not SMTP_PASSWORD:
            app.logger.warning('SMTP credentials not configured; skipping send_email')
            return False

        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if SMTP_PORT == 587:
                server.starttls()
                server.ehlo()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, [to_email], msg.as_string())

        return True
    except Exception as e:
        app.logger.exception('Email error: %s', e)
        return False

def calculate_attendance_percentage(student_id, class_id=None):
    query = Attendance.query.join(AttendanceSession).filter(
        Attendance.student_id == student_id
    )
    
    if class_id:
        query = query.filter(AttendanceSession.class_id == class_id)
    
    total_sessions = query.count()
    present_sessions = query.filter(Attendance.status.in_(['present', 'late'])).count()
    
    if total_sessions == 0:
        return 0
    
    return round((present_sessions / total_sessions) * 100, 2)


# Helper getters to ensure profile records exist for the logged-in user
def get_current_faculty():
    faculty = Faculty.query.filter_by(user_id=session.get('user_id')).first()
    if not faculty:
        session.clear()
        flash('Faculty profile not found. Please contact admin.', 'danger')
        return None
    return faculty


def get_current_student():
    student = Student.query.filter_by(user_id=session.get('user_id')).first()
    if not student:
        session.clear()
        flash('Student profile not found. Please contact admin.', 'danger')
        return None
    return student

# ==================== ROUTES ====================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password) and user.is_active:
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['full_name'] = user.full_name
            session['last_activity'] = datetime.now().isoformat()  # Set initial activity time
            
            log_audit('Login', 'User', user.id, f'User {username} logged in')
            
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            log_audit('Failed Login', 'User', None, f'Failed login attempt for {username}')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    username = session.get('username')
    log_audit('Logout', 'User', session.get('user_id'), f'User {username} logged out')
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/account/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    user = User.query.get_or_404(session['user_id'])

    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not check_password_hash(user.password_hash, current_password):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('change_password'))

        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'warning')
            return redirect(url_for('change_password'))

        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'warning')
            return redirect(url_for('change_password'))

        if check_password_hash(user.password_hash, new_password):
            flash('New password cannot be the same as the current password.', 'warning')
            return redirect(url_for('change_password'))

        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        log_audit('Change Password', 'User', user.id, 'Password updated by account holder')
        flash('Your password has been updated successfully.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('account/change_password.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    
    if user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif user.role == 'faculty':
        return redirect(url_for('faculty_dashboard'))
    elif user.role == 'student':
        return redirect(url_for('student_dashboard'))
    
    return render_template('dashboard.html')

# ==================== ADMIN ROUTES ====================

@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    total_students = Student.query.count()
    total_faculty = Faculty.query.count()
    total_courses = Course.query.count()
    total_classes = Class.query.count()
    
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html',
                         total_students=total_students,
                         total_faculty=total_faculty,
                         total_courses=total_courses,
                         total_classes=total_classes,
                         recent_logs=recent_logs)

@app.route('/admin/users')
@role_required('admin')
def admin_users():
    # Group users by role
    admins = User.query.filter_by(role='admin').all()
    faculty_users = User.query.filter_by(role='faculty').all()
    
    # Group students by section
    students_by_section = {}
    students = Student.query.join(User).all()
    for student in students:
        key = f"{student.department} - Year {student.year} - Section {student.section}"
        if key not in students_by_section:
            students_by_section[key] = []
        students_by_section[key].append(student)
    
    return render_template('admin/users.html', 
                         admins=admins,
                         faculty_users=faculty_users,
                         students_by_section=students_by_section)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@role_required('admin')
def admin_add_user():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role')
            full_name = request.form.get('full_name')
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists.', 'danger')
                return redirect(url_for('admin_add_user'))
            
            if User.query.filter_by(email=email).first():
                flash('Email already exists.', 'danger')
                return redirect(url_for('admin_add_user'))
            
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role=role,
                full_name=full_name
            )
            db.session.add(user)
            db.session.commit()
            
            if role == 'student':
                student_id = request.form.get('student_id')
                department = request.form.get('department')
                year = request.form.get('year')
                section = request.form.get('section')
                parent_email = request.form.get('parent_email')
                
                student = Student(
                    user_id=user.id,
                    student_id=student_id,
                    department=department,
                    year=year,
                    section=section,
                    parent_email=parent_email
                )
                db.session.add(student)
            
            elif role == 'faculty':
                faculty_id = request.form.get('faculty_id')
                department = request.form.get('department')
                designation = request.form.get('designation')
                
                faculty = Faculty(
                    user_id=user.id,
                    faculty_id=faculty_id,
                    department=department,
                    designation=designation
                )
                db.session.add(faculty)
            
            db.session.commit()
            
            log_audit('Create User', 'User', user.id, f'Created user {username} with role {role}')
            flash(f'User {username} created successfully!', 'success')
            return redirect(url_for('admin_users'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
    
    return render_template('admin/add_user.html')

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.role == 'admin' and User.query.filter_by(role='admin').count() <= 1:
        flash('Cannot delete the last admin user.', 'danger')
        return redirect(url_for('admin_users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    log_audit('Delete User', 'User', user_id, f'Deleted user {username}')
    flash(f'User {username} deleted successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/courses')
@role_required('admin')
def admin_courses():
    # Group courses by department
    courses_by_dept = {}
    courses = Course.query.all()
    for course in courses:
        if course.department not in courses_by_dept:
            courses_by_dept[course.department] = []
        courses_by_dept[course.department].append(course)
    
    return render_template('admin/courses.html', courses_by_dept=courses_by_dept)

@app.route('/admin/courses/add', methods=['GET', 'POST'])
@role_required('admin')
def admin_add_course():
    if request.method == 'POST':
        try:
            course_code = request.form.get('course_code')
            course_name = request.form.get('course_name')
            department = request.form.get('department')
            credits = request.form.get('credits')
            year = request.form.get('year')
            semester = request.form.get('semester')
            
            if Course.query.filter_by(course_code=course_code).first():
                flash('Course code already exists.', 'danger')
                return redirect(url_for('admin_add_course'))
            
            course = Course(
                course_code=course_code,
                course_name=course_name,
                department=department,
                credits=credits,
                year=year,
                semester=semester
            )
            db.session.add(course)
            db.session.commit()
            
            log_audit('Create Course', 'Course', course.id, f'Created course {course_code}')
            flash(f'Course {course_name} created successfully!', 'success')
            return redirect(url_for('admin_courses'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating course: {str(e)}', 'danger')
    
    return render_template('admin/add_course.html')

@app.route('/admin/classes')
@role_required('admin')
def admin_classes():
    classes = Class.query.all()
    return render_template('admin/classes.html', classes=classes)

@app.route('/admin/classes/add', methods=['GET', 'POST'])
@role_required('admin')
def admin_add_class():
    if request.method == 'POST':
        try:
            course_id = request.form.get('course_id')
            faculty_id = request.form.get('faculty_id')
            section = request.form.get('section')
            schedule = request.form.get('schedule')
            room = request.form.get('room')
            
            class_obj = Class(
                course_id=course_id,
                faculty_id=faculty_id,
                section=section,
                schedule=schedule,
                room=room
            )
            db.session.add(class_obj)
            db.session.commit()
            
            log_audit('Create Class', 'Class', class_obj.id, f'Created class for course {course_id}')
            flash('Class created successfully!', 'success')
            return redirect(url_for('admin_classes'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating class: {str(e)}', 'danger')
    
    courses = Course.query.all()
    faculty = Faculty.query.all()
    return render_template('admin/add_class.html', courses=courses, faculty=faculty)

@app.route('/admin/reports')
@role_required('admin')
def admin_reports():
    return render_template('admin/reports.html')

@app.route('/admin/reports/attendance')
@role_required('admin')
def admin_attendance_report():
    course_id = request.args.get('course_id', type=int)
    department = request.args.get('department')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = db.session.query(
        Student.student_id,
        User.full_name,
        Student.department,
        Student.section,
        Course.course_name,
        db.func.count(Attendance.id).label('total_sessions'),
        db.func.sum(db.case((Attendance.status.in_(['present', 'late']), 1), else_=0)).label('present_count')
    ).join(User, Student.user_id == User.id)\
     .join(Enrollment, Enrollment.student_id == Student.id)\
     .join(Class, Class.id == Enrollment.class_id)\
     .join(Course, Course.id == Class.course_id)\
     .join(AttendanceSession, AttendanceSession.class_id == Class.id)\
     .join(Attendance, Attendance.session_id == AttendanceSession.id)
    
    if course_id:
        query = query.filter(Course.id == course_id)
    if department:
        query = query.filter(Student.department == department)
    if start_date:
        query = query.filter(AttendanceSession.date >= start_date)
    if end_date:
        query = query.filter(AttendanceSession.date <= end_date)
    
    results = query.group_by(Student.id, Course.id).all()
    
    report_data = []
    for row in results:
        percentage = round((row.present_count / row.total_sessions * 100), 2) if row.total_sessions > 0 else 0
        report_data.append({
            'student_id': row.student_id,
            'name': row.full_name,
            'department': row.department,
            'section': row.section,
            'course': row.course_name,
            'total_sessions': row.total_sessions,
            'present': row.present_count,
            'percentage': percentage
        })
    
    courses = Course.query.all()
    departments = db.session.query(Student.department).distinct().all()
    
    return render_template('admin/attendance_report.html',
                         report_data=report_data,
                         courses=courses,
                         departments=[d[0] for d in departments])

# ==================== FACULTY ROUTES ====================

@app.route('/faculty/dashboard')
@role_required('faculty')
def faculty_dashboard():
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    my_classes = Class.query.filter_by(faculty_id=faculty.id).all()
    
    today = datetime.now().date()
    today_sessions = AttendanceSession.query.filter(
        AttendanceSession.class_id.in_([c.id for c in my_classes]),
        AttendanceSession.date == today
    ).all()
    
    return render_template('faculty/dashboard.html',
                         my_classes=my_classes,
                         today_sessions=today_sessions)

@app.route('/faculty/classes')
@role_required('faculty')
def faculty_classes():
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    my_classes = Class.query.filter_by(faculty_id=faculty.id).all()
    return render_template('faculty/classes.html', classes=my_classes)

@app.route('/faculty/class/<int:class_id>')
@role_required('faculty')
def faculty_class_detail(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    if class_obj.faculty_id != faculty.id:
        flash('You do not have access to this class.', 'danger')
        return redirect(url_for('faculty_classes'))
    
    enrollments = Enrollment.query.filter_by(class_id=class_id).all()
    sessions = AttendanceSession.query.filter_by(class_id=class_id)\
                                     .order_by(AttendanceSession.date.desc()).all()
    
    return render_template('faculty/class_detail.html',
                         class_obj=class_obj,
                         enrollments=enrollments,
                         sessions=sessions)

@app.route('/faculty/attendance/create', methods=['GET', 'POST'])
@role_required('faculty')
def faculty_create_session():
    if request.method == 'POST':
        try:
            class_id = request.form.get('class_id')
            date_str = request.form.get('date')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            
            session_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
            end_time_obj = datetime.strptime(end_time_str, '%H:%M').time()
            
            session_obj = AttendanceSession(
                class_id=class_id,
                date=session_date,
                start_time=start_time_obj,
                end_time=end_time_obj,
                created_by=session['user_id']
            )
            db.session.add(session_obj)
            db.session.commit()
            
            log_audit('Create Session', 'AttendanceSession', session_obj.id, 
                     f'Created attendance session for class {class_id}')
            
            flash('Attendance session created successfully! Now you can mark attendance.', 'success')
            return redirect(url_for('faculty_mark_attendance_page', session_id=session_obj.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating session: {str(e)}', 'danger')
    
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    my_classes = Class.query.filter_by(faculty_id=faculty.id).all()
    return render_template('faculty/create_session.html', classes=my_classes)

@app.route('/faculty/session/<int:session_id>/mark')
@role_required('faculty')
def faculty_mark_attendance_page(session_id):
    session_obj = AttendanceSession.query.get_or_404(session_id)
    
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    if session_obj.class_ref.faculty_id != faculty.id:
        flash('You do not have access to this session.', 'danger')
        return redirect(url_for('faculty_classes'))
    
    enrollments = Enrollment.query.filter_by(class_id=session_obj.class_id).all()
    
    attendance_records = {
        record.student_id: record 
        for record in Attendance.query.filter_by(session_id=session_id).all()
    }
    
    return render_template('faculty/mark_attendance.html',
                         session_obj=session_obj,
                         enrollments=enrollments,
                         attendance_records=attendance_records)

@app.route('/faculty/session/<int:session_id>')
@role_required('faculty')
def faculty_session_detail(session_id):
    """Proxy route kept for backwards compatibility; reuse mark_attendance view."""
    return redirect(url_for('faculty_mark_attendance_page', session_id=session_id))

@app.route('/faculty/attendance/mark', methods=['POST'])
@role_required('faculty')
def faculty_mark_attendance():
    try:
        session_id = request.form.get('session_id')
        student_id = request.form.get('student_id')
        status = request.form.get('status')
        # Ensure faculty has permission to modify this session
        session_obj = AttendanceSession.query.get(session_id)
        faculty = get_current_faculty()
        if not faculty:
            return jsonify({'success': False, 'message': 'Faculty profile not found'}), 403

        if not session_obj or session_obj.class_ref.faculty_id != faculty.id:
            return jsonify({'success': False, 'message': 'Unauthorized access to this session'}), 403

        existing = Attendance.query.filter_by(
            session_id=session_id,
            student_id=student_id
        ).first()
        
        if existing:
            existing.status = status
            existing.marked_at = datetime.utcnow()
            existing.marked_by = session['user_id']
            existing.method = 'manual'
        else:
            attendance = Attendance(
                session_id=session_id,
                student_id=student_id,
                status=status,
                marked_by=session['user_id'],
                method='manual'
            )
            db.session.add(attendance)
        
        db.session.commit()

        # Check for low attendance and send notification
        if status == 'absent':
            student = Student.query.get(student_id)
            percentage = calculate_attendance_percentage(student_id, session_obj.class_id)

            if percentage < 75:
                # Create notification for student
                notification = Notification(
                    user_id=student.user_id,
                    title='⚠️ Low Attendance Alert',
                    message=f'Your attendance in {session_obj.class_ref.course.course_name} has dropped to {percentage}%. You need to maintain at least 75% attendance to be eligible for exams. Please attend classes regularly.',
                    type='low_attendance'
                )
                db.session.add(notification)
                db.session.commit()

        # Audit: log with the attendance id when possible
        attendance_id = existing.id if existing else attendance.id
        log_audit('Mark Attendance', 'Attendance', attendance_id,
                 f'Set status={status} for student {student_id} in session {session_id} by faculty {faculty.id}')

        return jsonify({'success': True, 'message': 'Attendance marked successfully', 'attendance_id': attendance_id})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/faculty/reports')
@role_required('faculty')
def faculty_reports():
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    my_classes = Class.query.filter_by(faculty_id=faculty.id).all()
    return render_template('faculty/reports.html', classes=my_classes)

@app.route('/faculty/reports/class/<int:class_id>')
@role_required('faculty')
def faculty_class_report(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    if class_obj.faculty_id != faculty.id:
        flash('You do not have access to this class.', 'danger')
        return redirect(url_for('faculty_classes'))
    
    enrollments = Enrollment.query.filter_by(class_id=class_id).all()
    
    report_data = []
    for enrollment in enrollments:
        student = enrollment.student
        percentage = calculate_attendance_percentage(student.id, class_id)
        
        total = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            Attendance.student_id == student.id
        ).count()
        
        present = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            Attendance.student_id == student.id,
            Attendance.status.in_(['present', 'late'])
        ).count()
        
        report_data.append({
            'student_id': student.student_id,
            'name': student.user.full_name,
            'total': total,
            'present': present,
            'absent': total - present,
            'percentage': percentage
        })
    
    return render_template('faculty/class_report.html',
                         class_obj=class_obj,
                         report_data=report_data)

@app.route('/faculty/export/csv/<int:class_id>')
@role_required('faculty')
def faculty_export_csv(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    if class_obj.faculty_id != faculty.id:
        flash('You do not have access to this class.', 'danger')
        return redirect(url_for('faculty_classes'))
    
    enrollments = Enrollment.query.filter_by(class_id=class_id).all()
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Student ID', 'Name', 'Total Sessions', 'Present', 'Absent', 'Percentage'])
    
    for enrollment in enrollments:
        student = enrollment.student
        percentage = calculate_attendance_percentage(student.id, class_id)
        
        total = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            Attendance.student_id == student.id
        ).count()
        
        present = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            Attendance.student_id == student.id,
            Attendance.status.in_(['present', 'late'])
        ).count()
        
        writer.writerow([
            student.student_id,
            student.user.full_name,
            total,
            present,
            total - present,
            f"{percentage}%"
        ])
    
    output = BytesIO()
    output.write(si.getvalue().encode())
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_report_{class_obj.course.course_code}.csv'
    )

@app.route('/faculty/export/pdf/<int:class_id>')
@role_required('faculty')
def faculty_export_pdf(class_id):
    class_obj = Class.query.get_or_404(class_id)
    
    faculty = get_current_faculty()
    if not faculty:
        return redirect(url_for('login'))
    if class_obj.faculty_id != faculty.id:
        flash('You do not have access to this class.', 'danger')
        return redirect(url_for('faculty_classes'))
    
    enrollments = Enrollment.query.filter_by(class_id=class_id).all()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # FIXED: Better heading with course and section info
    title = Paragraph(f"Attendance Report - {class_obj.course.course_name} (Section {class_obj.section})", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.3*inch))
    
    subtitle = Paragraph(f"Course Code: {class_obj.course.course_code} | Faculty: {class_obj.faculty.user.full_name}", styles['Normal'])
    elements.append(subtitle)
    elements.append(Spacer(1, 0.3*inch))
    
    data = [['Student ID', 'Name', 'Total', 'Present', 'Absent', 'Percentage']]
    
    for enrollment in enrollments:
        student = enrollment.student
        percentage = calculate_attendance_percentage(student.id, class_id)
        
        total = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            Attendance.student_id == student.id
        ).count()
        
        present = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_id,
            Attendance.student_id == student.id,
            Attendance.status.in_(['present', 'late'])
        ).count()
        
        data.append([
            student.student_id,
            student.user.full_name,
            str(total),
            str(present),
            str(total - present),
            f"{percentage}%"
        ])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'attendance_report_{class_obj.course.course_code}_Section{class_obj.section}.pdf'
    )

# ==================== STUDENT ROUTES ====================

@app.route('/student/dashboard')
@role_required('student')
def student_dashboard():
    student = get_current_student()
    if not student:
        return redirect(url_for('login'))

    enrollments = Enrollment.query.filter_by(student_id=student.id).all()
    
    attendance_summary = []
    for enrollment in enrollments:
        class_obj = enrollment.class_ref
        percentage = calculate_attendance_percentage(student.id, class_obj.id)
        
        total = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_obj.id,
            Attendance.student_id == student.id
        ).count()
        
        present = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.class_id == class_obj.id,
            Attendance.student_id == student.id,
            Attendance.status.in_(['present', 'late'])
        ).count()
        
        attendance_summary.append({
            'class': class_obj,
            'total': total,
            'present': present,
            'percentage': percentage
        })
    
    # Get unread notifications
    unread_count = Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).count()
    
    notifications = Notification.query.filter_by(user_id=session['user_id'])\
                                     .order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('student/dashboard.html',
                         student=student,
                         attendance_summary=attendance_summary,
                         notifications=notifications,
                         unread_count=unread_count)

@app.route('/student/attendance')
@role_required('student')
def student_attendance():
    student = get_current_student()
    if not student:
        return redirect(url_for('login'))
    enrollments = Enrollment.query.filter_by(student_id=student.id).all()
    
    return render_template('student/attendance.html',
                         student=student,
                         enrollments=enrollments)

@app.route('/student/attendance/<int:class_id>')
@role_required('student')
def student_class_attendance(class_id):
    student = get_current_student()
    if not student:
        return redirect(url_for('login'))
    class_obj = Class.query.get_or_404(class_id)
    
    enrollment = Enrollment.query.filter_by(student_id=student.id, class_id=class_id).first()
    if not enrollment:
        flash('You are not enrolled in this class.', 'danger')
        return redirect(url_for('student_attendance'))
    
    records = db.session.query(AttendanceSession, Attendance)\
        .outerjoin(Attendance, db.and_(
            Attendance.session_id == AttendanceSession.id,
            Attendance.student_id == student.id
        ))\
        .filter(AttendanceSession.class_id == class_id)\
        .order_by(AttendanceSession.date.desc()).all()
    
    percentage = calculate_attendance_percentage(student.id, class_id)
    
    return render_template('student/class_attendance.html',
                         class_obj=class_obj,
                         records=records,
                         percentage=percentage)

@app.route('/student/notifications')
@role_required('student')
def student_notifications():
    notifications = Notification.query.filter_by(user_id=session['user_id'])\
                                     .order_by(Notification.created_at.desc()).all()

    # Mark all as read
    for notif in notifications:
        notif.is_read = True
    db.session.commit()

    return render_template('student/notifications.html', notifications=notifications)

# ==================== API ROUTES ====================

@app.route('/api/attendance/update', methods=['POST'])
@role_required('faculty')
def api_update_attendance():
    """API endpoint for faculty to update attendance after it's been marked"""
    try:
        data = request.get_json()
        attendance_id = data.get('attendance_id')
        new_status = data.get('status')
        
        attendance = Attendance.query.get_or_404(attendance_id)
        
        # Verify faculty has access to this attendance record
        faculty = Faculty.query.filter_by(user_id=session['user_id']).first()
        session_obj = AttendanceSession.query.get(attendance.session_id)
        
        if session_obj.class_ref.faculty_id != faculty.id:
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
        # Update the attendance
        attendance.status = new_status
        attendance.marked_at = datetime.utcnow()
        attendance.marked_by = session['user_id']
        db.session.commit()
        
        log_audit('Update Attendance', 'Attendance', attendance_id, 
                 f'Updated attendance status to {new_status}')
        # Return the affected student id and new status so the UI can update without a reload
        return jsonify({'success': True, 'message': 'Attendance updated successfully', 'attendance_id': attendance_id, 'student_id': attendance.student_id, 'status': attendance.status})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

# ==================== INITIALIZE DATABASE ====================

def init_db():
    with app.app_context():
        db.create_all()
        
        if not User.query.filter_by(role='admin').first():
            print("\n🔄 Initializing database with organized structure...")
            
            # Create admin
            admin = User(
                username='admin',
                email='admin@sams.edu',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                full_name='System Administrator'
            )
            db.session.add(admin)
            db.session.commit()
            
            # Create 5 faculty members (organized by department)
            faculty_data = [
                {'name': 'Dr. Sarah Johnson', 'dept': 'Computer Science', 'designation': 'Professor'},
                {'name': 'Prof. Michael Chen', 'dept': 'Computer Science', 'designation': 'Associate Professor'},
                {'name': 'Dr. Emily Williams', 'dept': 'Information Technology', 'designation': 'Assistant Professor'},
                {'name': 'Prof. Robert Davis', 'dept': 'Computer Science', 'designation': 'Professor'},
                {'name': 'Dr. Lisa Anderson', 'dept': 'Information Technology', 'designation': 'Associate Professor'}
            ]
            
            faculty_list = []
            for i, fac_data in enumerate(faculty_data, 1):
                faculty_user = User(
                    username=f'faculty{i}',
                    email=f'faculty{i}@sams.edu',
                    password_hash=generate_password_hash('faculty123'),
                    role='faculty',
                    full_name=fac_data['name']
                )
                db.session.add(faculty_user)
                db.session.commit()
                
                faculty = Faculty(
                    user_id=faculty_user.id,
                    faculty_id=f'FAC{str(i).zfill(3)}',
                    department=fac_data['dept'],
                    designation=fac_data['designation']
                )
                db.session.add(faculty)
                faculty_list.append(faculty)
            
            db.session.commit()
            print("✓ Created 5 faculty members")
            
            # Create 12 courses (organized by department and year)
            courses_data = [
                # Computer Science - 7 courses
                {'code': 'CS101', 'name': 'Introduction to Programming', 'dept': 'Computer Science', 'credits': 4, 'year': 1, 'sem': 1},
                {'code': 'CS102', 'name': 'Data Structures', 'dept': 'Computer Science', 'credits': 4, 'year': 1, 'sem': 2},
                {'code': 'CS201', 'name': 'Database Management Systems', 'dept': 'Computer Science', 'credits': 3, 'year': 2, 'sem': 1},
                {'code': 'CS202', 'name': 'Operating Systems', 'dept': 'Computer Science', 'credits': 4, 'year': 2, 'sem': 2},
                {'code': 'CS301', 'name': 'Machine Learning', 'dept': 'Computer Science', 'credits': 3, 'year': 3, 'sem': 1},
                {'code': 'CS302', 'name': 'Artificial Intelligence', 'dept': 'Computer Science', 'credits': 4, 'year': 3, 'sem': 2},
                {'code': 'CS303', 'name': 'Software Engineering', 'dept': 'Computer Science', 'credits': 3, 'year': 3, 'sem': 1},
                # Information Technology - 5 courses
                {'code': 'IT101', 'name': 'Web Technologies', 'dept': 'Information Technology', 'credits': 3, 'year': 1, 'sem': 1},
                {'code': 'IT102', 'name': 'Computer Networks', 'dept': 'Information Technology', 'credits': 4, 'year': 1, 'sem': 2},
                {'code': 'IT201', 'name': 'Cloud Computing', 'dept': 'Information Technology', 'credits': 3, 'year': 2, 'sem': 1},
                {'code': 'IT202', 'name': 'Cybersecurity', 'dept': 'Information Technology', 'credits': 3, 'year': 2, 'sem': 2},
                {'code': 'IT301', 'name': 'DevOps and CI/CD', 'dept': 'Information Technology', 'credits': 3, 'year': 3, 'sem': 1}
            ]
            
            courses_list = []
            for course_data in courses_data:
                course = Course(
                    course_code=course_data['code'],
                    course_name=course_data['name'],
                    department=course_data['dept'],
                    credits=course_data['credits'],
                    year=course_data['year'],
                    semester=course_data['sem']
                )
                db.session.add(course)
                courses_list.append(course)
            
            db.session.commit()
            print("✓ Created 12 courses (7 CS + 5 IT)")
            
            # FIXED: Organized class creation matching course years
            print("\n🎓 Creating organized class structure...")
            print("   6 Sections across 3 years × 2 courses each = 12 Classes")
            
            # Define sections with their respective years
            section_year_mapping = {
                'A': 1, 'B': 1,  # Year 1 sections
                'C': 2, 'D': 2,  # Year 2 sections
                'E': 3, 'F': 3   # Year 3 sections
            }
            
            rooms = ['Lab 101', 'Lab 102', 'Lab 103', 'Room 201', 'Room 202', 'Room 203']
            schedules = ['MWF 09:00-10:00', 'MWF 10:00-11:00', 'MWF 11:00-12:00', 
                        'TTS 09:00-10:00', 'TTS 10:00-11:00', 'TTS 11:00-12:00']
            
            classes_list = []
            for section, year in section_year_mapping.items():
                # Get courses for this year
                year_courses = [c for c in courses_list if c.year == year]
                # Select 2 courses for this section
                selected_courses = random.sample(year_courses, min(2, len(year_courses)))
                
                for course in selected_courses:
                    # Assign faculty based on department
                    dept_faculty = [f for f in faculty_list if f.department == course.department]
                    assigned_faculty = random.choice(dept_faculty)
                    
                    class_obj = Class(
                        course_id=course.id,
                        faculty_id=assigned_faculty.id,
                        section=section,
                        schedule=random.choice(schedules),
                        room=random.choice(rooms)
                    )
                    db.session.add(class_obj)
                    classes_list.append(class_obj)
            
            db.session.commit()
            print(f"✓ Created {len(classes_list)} classes (across Years 1, 2, 3)")
            
            # Create 240 students (40 per section, 6 sections)
            print("\n👥 Creating students...")
            first_names = ['James', 'Mary', 'John', 'Patricia', 'Robert', 'Jennifer', 'Michael', 'Linda', 
                          'William', 'Barbara', 'David', 'Elizabeth', 'Richard', 'Susan', 'Joseph', 'Jessica',
                          'Thomas', 'Sarah', 'Charles', 'Karen', 'Christopher', 'Nancy', 'Daniel', 'Lisa',
                          'Matthew', 'Betty', 'Anthony', 'Margaret', 'Mark', 'Sandra', 'Donald', 'Ashley',
                          'Steven', 'Kimberly', 'Paul', 'Emily', 'Andrew', 'Donna', 'Joshua', 'Michelle']
            
            last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
                         'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
                         'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White']
            
            student_count = 1
            for section, year in section_year_mapping.items():
                print(f"   Section {section} (Year {year}): Creating 40 students...")
                
                for i in range(40):
                    full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
                    student_user = User(
                        username=f'student{student_count}',
                        email=f'student{student_count}@sams.edu',
                        password_hash=generate_password_hash('student123'),
                        role='student',
                        full_name=full_name
                    )
                    db.session.add(student_user)
                    db.session.commit()
                    
                    # Determine department based on section
                    dept = 'Computer Science' if section in ['A', 'B', 'C'] else 'Information Technology'
                    
                    student = Student(
                        user_id=student_user.id,
                        student_id=f'STU{str(student_count).zfill(4)}',
                        department=dept,
                        year=year,  # FIXED: Use the correct year based on section
                        section=section,
                        parent_email=f'parent{student_count}@example.com'
                    )
                    db.session.add(student)
                    db.session.commit()
                    
                    # Enroll student in all courses of their section (matching year)
                    section_classes = [c for c in classes_list if c.section == section]
                    for class_obj in section_classes:
                        enrollment = Enrollment(
                            student_id=student.id,
                            class_id=class_obj.id
                        )
                        db.session.add(enrollment)
                    
                    student_count += 1
                
                db.session.commit()
            
            print(f"✓ Created {student_count - 1} students (40 per section × 6 sections)")
            print("✓ Each student enrolled in 2 courses matching their year")
            
            # Generate 30 days of attendance data
            print("\n📅 Generating 30 days of attendance records...")
            today = datetime.now().date()
            
            for day_offset in range(30):
                current_date = today - timedelta(days=day_offset)
                
                # Skip weekends
                if current_date.weekday() >= 5:
                    continue
                
                for class_obj in classes_list:
                    # Create session for each class
                    session_obj = AttendanceSession(
                        class_id=class_obj.id,
                        date=current_date,
                        start_time=time(9, 0),
                        end_time=time(10, 0),
                        created_by=class_obj.faculty.user_id,
                        is_active=False  # Past sessions are inactive
                    )
                    db.session.add(session_obj)
                    db.session.commit()
                    
                    # Mark attendance for all enrolled students
                    enrollments = Enrollment.query.filter_by(class_id=class_obj.id).all()
                    for enrollment in enrollments:
                        # 85% present, 10% late, 5% absent (realistic distribution)
                        rand = random.random()
                        if rand < 0.85:
                            status = 'present'
                        elif rand < 0.95:
                            status = 'late'
                        else:
                            status = 'absent'
                        
                        attendance = Attendance(
                            session_id=session_obj.id,
                            student_id=enrollment.student_id,
                            status=status,
                            marked_by=class_obj.faculty.user_id,
                            method='manual'
                        )
                        db.session.add(attendance)
                
                db.session.commit()
            
            print("✓ Generated 30 days of attendance (weekdays only)")
            
            # Generate notifications for low attendance students
            print("\n🔔 Generating notifications for low attendance...")
            notification_count = 0
            for student in Student.query.all():
                for enrollment in student.enrollments:
                    percentage = calculate_attendance_percentage(student.id, enrollment.class_id)
                    if percentage < 75:
                        notification = Notification(
                            user_id=student.user_id,
                            title='⚠️ Low Attendance Alert',
                            message=f'Your attendance in {enrollment.class_ref.course.course_name} is {percentage}%. You need at least 75% to be eligible for exams.',
                            type='low_attendance'
                        )
                        db.session.add(notification)
                        notification_count += 1
            
            db.session.commit()
            print(f"✓ Created {notification_count} notifications")
            
            # Print summary
            print("\n" + "="*70)
            print("DATABASE INITIALIZED SUCCESSFULLY!")
            print("="*70)
            print("\n📊 Database Statistics:")
            print(f"  ✓ Total Users: {User.query.count()}")
            print(f"  ✓ Admins: {User.query.filter_by(role='admin').count()}")
            print(f"  ✓ Faculty: {Faculty.query.count()}")
            print(f"  ✓ Students: {Student.query.count()}")
            print(f"  ✓ Courses: {Course.query.count()}")
            print(f"  ✓ Classes: {Class.query.count()}")
            print(f"  ✓ Enrollments: {Enrollment.query.count()}")
            print(f"  ✓ Attendance Sessions: {AttendanceSession.query.count()}")
            print(f"  ✓ Attendance Records: {Attendance.query.count()}")
            print(f"  ✓ Notifications: {Notification.query.count()}")
            
            print("\n🎓 Structure:")
            print("  • 6 Sections (A, B = Year 1; C, D = Year 2; E, F = Year 3)")
            print("  • 40 Students per section = 240 total")
            print("  • Each section takes 2 courses matching their year")
            print("  • 30 days of attendance generated")
            
            print("\n🔐 Login Credentials:")
            print("  Admin:")
            print("    Username: admin")
            print("    Password: admin123")
            print("\n  Faculty (any of these):")
            for i in range(1, 6):
                print(f"    Username: faculty{i}")
                print(f"    Password: faculty123")
            print("\n  Students:")
            print("    Username: student1 to student240")
            print("    Password: student123")
            print("="*70 + "\n")

if __name__ == '__main__':
    init_db()
    # Read debug flag from environment so production doesn't accidentally enable the debugger
    debug_env = os.environ.get('FLASK_DEBUG', os.environ.get('DEBUG', 'False'))
    debug = str(debug_env).lower() in ('1', 'true', 'yes')
    app.run(debug=debug, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))