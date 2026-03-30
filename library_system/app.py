import os
import face_recognition
import pickle
import numpy as np
import base64
import io
import re
import pytesseract
import cv2
import pyrxing
from PIL import Image, ImageOps, ImageFilter
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import db, Admin, Student, Book, Transaction

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "professional-library-secret-2025")

# Use absolute paths for instance folder to avoid WinError 5 or path mismatches
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)

DB_PATH = os.path.join(INSTANCE_DIR, 'library.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- OCR Setup ---
# Relying on system PATH for Tesseract
import pytesseract

# --- Biometric Helpers ---

def get_face_encoding_from_base64(base64_str):
    """Processes base64 image string, detects face, and returns encoding."""
    try:
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]
            
        img_data = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(img_data)).convert('RGB')
        img_array = np.array(img)
        
        face_locations = face_recognition.face_locations(img_array)
        if len(face_locations) == 1:
            encodings = face_recognition.face_encodings(img_array, face_locations)
            if encodings:
                return encodings[0]
        elif len(face_locations) > 1:
            return "MULTIPLE_FACES"
    except Exception as e:
        print(f"Error processing face: {e}")
    return None

def is_valid_isbn_10(isbn):
    """Checks if a string is a valid ISBN-10."""
    if len(isbn) != 10:
        return False
    digits = []
    for char in isbn:
        if char == 'X':
            digits.append(10)
        else:
            digits.append(int(char))
    
    total = sum((10 - i) * digit for i, digit in enumerate(digits))
    return total % 11 == 0

def is_valid_isbn_13(isbn):
    """Checks if a string is a valid ISBN-13."""
    if len(isbn) != 13:
        return False
    digits = [int(d) for d in isbn]
    total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    return total % 10 == 0

def fix_ocr_mistakes(text):
    """Corrects common OCR character misreads for digits."""
    replacements = {
        'O': '0', 'o': '0',
        'I': '1', 'i': '1', 'l': '1', '|': '1',
        'S': '5', 's': '5',
        'Z': '2', 'z': '2',
        'B': '8', 'G': '6', 'T': '7',
        'g': '9', 'q': '9'
    }
    corrected = ""
    for char in text:
        if char in replacements:
            corrected += replacements[char]
        else:
            corrected += char
    return corrected

def extract_isbn_from_base64(base64_str):
    try:
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]

        img_data = base64.b64decode(base64_str)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # --- PASS 1: PYRXING BARCODE SCANNING (100% ACCURACY) ---
        # Robust, faster, and dependency-free alternative for Windows
        try:
            pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            results = pyrxing.read_barcodes(pil_img)
            for res in results:
                isbn_cand = res.text
                if isbn_cand:
                    # Clean and validate
                    clean_cand = "".join(filter(str.isdigit, isbn_cand))
                    if is_valid_isbn_13(clean_cand) or is_valid_isbn_10(clean_cand):
                        print(f"[BARCODE SUCCESS] Detected: {clean_cand}")
                        return clean_cand
        except Exception as e:
            print(f"[BARCODE ERROR] pyrxing failed: {e}")

        # --- PASS 2: ROBUST FALLBACK OCR (ONLY IF BARCODE FAILS) ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        
        # Test regions for different framing
        rois = [
            ("ROI_40", gray[int(height * 0.6):height, 0:width]),
            ("ROI_60", gray[int(height * 0.4):height, 0:width]),
            ("Full", gray)
        ]

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        candidates_10 = []

        for p_name, roi_img in rois:
            if roi_img.size == 0: continue
            
            enhanced = clahe.apply(roi_img)
            resized = cv2.resize(enhanced, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
            
            # Sub-Passes for extreme lighting conditions
            sub_passes = [
                ("Standard", resized),
                ("Inverted", cv2.bitwise_not(resized)), # Reads through bright white glare
                ("Sharpened", cv2.filter2D(resized, -1, np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])))
            ]

            for s_name, proc_img in sub_passes:
                # Binary strategies
                thresholds = [
                    ("Otsu", cv2.threshold(proc_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
                    ("Adaptive", cv2.adaptiveThreshold(proc_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2))
                ]

                for t_name, thresh_img in thresholds:
                    for psm in [7, 6, 3]: # Single line -> Block -> Auto
                        try:
                            config = f"--psm {psm} --oem 1 -c tessedit_char_whitelist=0123456789Xx"
                            text = pytesseract.image_to_string(thresh_img, config=config)
                            cleaned = fix_ocr_mistakes("".join(text.split()).replace("-", ""))
                            
                            # 1. 13-Digit Validation (Support regional codes like 890)
                            matches13 = re.findall(r"(\d{13})", cleaned)
                            for m in matches13:
                                if is_valid_isbn_13(m):
                                    print(f"[OCR SUCCESS] 13rd Pass ({p_name}/{s_name}/{t_name}): {m}")
                                    return m
                            
                            # 2. 10-Digit Validation (Store for later if no 13-digit found)
                            matches10 = re.findall(r"\d{9}[Xx]|\d{10}", cleaned)
                            for m in matches10:
                                m = m.upper()
                                if is_valid_isbn_10(m) and len(m) == 10:
                                    # Very high confidence check for ISBN-10 to avoid noise
                                    if psm == 7: # Single line mode is highest confidence for 10 digits
                                        candidates_10.append(m)
                        except: continue

        if candidates_10:
            return candidates_10[0]

        return {"error": "Detection failed. Tip: Hold the barcode steady in the center of the camera."}

    except Exception as e:
        return {"error": str(e)}

# --- Helpers ---

def clean_isbn(isbn):
    return "".join(filter(str.isdigit, isbn))

def validate_isbn(isbn):
    return len(isbn) in [10, 13]

def get_stats():
    total_books = db.session.query(db.func.sum(Book.total_copies)).scalar() or 0
    available_books = db.session.query(db.func.sum(Book.available_copies)).scalar() or 0
    issued_books = total_books - available_books
    
    total_transactions = Transaction.query.count()
    total_fine = db.session.query(db.func.sum(Transaction.fine)).scalar() or 0.0
    
    overdue_count = Transaction.query.filter(
        Transaction.return_date == None,
        Transaction.due_date < datetime.utcnow()
    ).count()
    
    return {
        "total_books": total_books,
        "available_books": available_books,
        "issued_books": issued_books,
        "overdue_count": overdue_count,
        "total_transactions": total_transactions,
        "total_fine": total_fine
    }

# --- Routes ---

@app.route('/')
def index():
    if 'admin_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and check_password_hash(admin.password_hash, password):
            # Temporarily store admin_id to verify face next
            session['pending_admin_id'] = admin.id
            return redirect(url_for('admin_face_verify'))
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/admin-face-verify', methods=['GET', 'POST'])
def admin_face_verify():
    admin_id = session.get('pending_admin_id')
    if not admin_id:
        return redirect(url_for('login'))
        
    admin = Admin.query.get(admin_id)
    
    if request.method == 'POST':
        image_data = request.form.get('image_data')
        encoding = get_face_encoding_from_base64(image_data)
        
        if isinstance(encoding, str) and encoding == "MULTIPLE_FACES":
            flash("Multiple faces detected. Please scan alone.", "warning")
        elif encoding is not None and not isinstance(encoding, str):
            if admin.face_encoding:
                # Compare
                stored_encoding = pickle.loads(admin.face_encoding)
                match = face_recognition.compare_faces([stored_encoding], encoding, tolerance=0.5)[0]
                if match:
                    session.pop('pending_admin_id', None)
                    session['admin_id'] = admin.id
                    flash("Biometric Login Successful!", "success")
                    return redirect(url_for('dashboard'))
                else:
                    flash("Face mismatch. Access denied.", "danger")
                    return redirect(url_for('login'))
            else:
                # First time registration
                admin.face_encoding = pickle.dumps(encoding)
                db.session.commit()
                session.pop('pending_admin_id', None)
                session['admin_id'] = admin.id
                flash("Face registered. Login successful!", "success")
                return redirect(url_for('dashboard'))
        else:
            flash("No face detected. Please try again.", "warning")
            
    return render_template('face_capture.html', title="Admin Face ID", subtitle="2-Step Verification Required", target_route=url_for('admin_face_verify'))

@app.route('/logout')
def logout():
    session.pop('admin_id', None)
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    
    stats = get_stats()
    return render_template('dashboard.html', **stats)

@app.route('/add-book', methods=['GET', 'POST'])
def add_book():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        isbn = clean_isbn(request.form.get('isbn'))
        copies = int(request.form.get('copies', 1))
        
        if not validate_isbn(isbn):
            flash("Invalid ISBN. Must be 10 or 13 digits.", "danger")
            return redirect(url_for('add_book'))
            
        book = Book.query.filter_by(isbn=isbn).first()
        if book:
            book.total_copies += copies
            book.available_copies += copies
            flash(f"Updated copies for '{title}'.", "success")
        else:
            new_book = Book(title=title, author=author, isbn=isbn, total_copies=copies, available_copies=copies)
            db.session.add(new_book)
            flash(f"Book '{title}' added successfully.", "success")
        
        db.session.commit()
        return redirect(url_for('dashboard'))
        
    return render_template('add_book.html')

@app.route('/scan-isbn', methods=['POST'])
def scan_isbn():
    if 'admin_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json()
    image_data = data.get('image_data')
    
    if not image_data:
        return jsonify({"error": "No image data", "status": "fail"}), 400
        
    result = extract_isbn_from_base64(image_data)
    
    if isinstance(result, str):
        return jsonify({"isbn": result, "status": "success"})
    else:
        return jsonify({"error": result.get("error", "No ISBN detected."), "status": "fail"})

@app.route('/process-isbn', methods=['POST'])
def process_isbn():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
        
    isbn = clean_isbn(request.form.get('isbn'))
    if not validate_isbn(isbn):
        flash("Invalid ISBN format.", "danger")
        return redirect(url_for('dashboard'))
        
    book = Book.query.filter_by(isbn=isbn).first()
    
    # Check if book exists in local database only
    if not book:
        flash("Book not found in library database. Please add the book first.", "danger")
        return redirect(url_for('dashboard'))
        
    return render_template('dashboard.html', selected_book=book, **get_stats())

@app.route('/issue-book/<int:book_id>', methods=['POST'])
def issue_book(book_id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))
        
    student_name = request.form.get('student_name')
    student_phone = request.form.get('student_phone')
    
    book = Book.query.get_or_404(book_id)
    if book.available_copies < 1:
        flash("No copies available.", "danger")
        return redirect(url_for('dashboard'))
        
    student = Student.query.filter_by(phone=student_phone).first()
    
    # Redirect to specialized web capture for student
    return render_template('face_capture.html', 
                          title="Student Verification", 
                          subtitle=f"Identity Check for {student_name}" if not student else f"Verify {student.name}",
                          target_route=url_for('verify_student_transaction'),
                          student_phone=student_phone,
                          student_name=student_name,
                          book_id=book_id,
                          action="issue")

@app.route('/verify-student-transaction', methods=['POST'])
def verify_student_transaction():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
        
    image_data = request.form.get('image_data')
    phone = request.form.get('student_phone')
    name = request.form.get('student_name')
    book_id = request.form.get('book_id')
    isbn = request.form.get('isbn') # For returns
    action = request.form.get('action')
    
    encoding = get_face_encoding_from_base64(image_data)
    
    # Handle failure or multiple faces safely (prevent numpy ValueError)
    if encoding is None:
        flash("No face detected. Try again.", "danger")
        return redirect(url_for('dashboard'))
        
    if isinstance(encoding, str) and encoding == "MULTIPLE_FACES":
        flash("Multiple faces detected. Please scan alone.", "danger")
        return redirect(url_for('dashboard'))
        
    student = Student.query.filter_by(phone=phone).first()
    
    if action == "issue":
        if not student:
            # Register new student
            student = Student(name=name, phone=phone, face_encoding=pickle.dumps(encoding))
            db.session.add(student)
            db.session.flush()
        else:
            # Verify
            stored = pickle.loads(student.face_encoding)
            match = face_recognition.compare_faces([stored], encoding, tolerance=0.5)[0]
            if not match:
                flash("Biometric Mismatch. Issuance blocked.", "danger")
                return redirect(url_for('dashboard'))
        
        book = Book.query.get(book_id)
        trans = Transaction(student_id=student.id, book_id=book.id, due_date=datetime.utcnow() + timedelta(days=7))
        book.available_copies -= 1
        db.session.add(trans)
        db.session.commit()
        flash(f"Book issued to {student.name}.", "success")
        
    elif action == "return":
        book = Book.query.filter_by(isbn=isbn).first()
        if not student or not book:
            flash("Invalid data.", "danger")
            return redirect(url_for('dashboard'))
            
        stored = pickle.loads(student.face_encoding)
        match = face_recognition.compare_faces([stored], encoding, tolerance=0.5)[0]
        if not match:
            flash("Biometric Mismatch. Return denied.", "danger")
            return redirect(url_for('dashboard'))
            
        trans = Transaction.query.filter_by(student_id=student.id, book_id=book.id, return_date=None).first()
        if trans:
            trans.return_date = datetime.utcnow()
            if trans.return_date > trans.due_date:
                trans.fine = (trans.return_date - trans.due_date).days * 5.0
            book.available_copies += 1
            db.session.commit()
            flash(f"Book returned. Fine: ₹{trans.fine}", "success")
        else:
            flash("No active transaction found.", "warning")
            
    return redirect(url_for('dashboard'))

@app.route('/return-book', methods=['POST'])
def return_book():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
        
    student_phone = request.form.get('student_phone')
    isbn = clean_isbn(request.form.get('isbn'))
    
    book = Book.query.filter_by(isbn=isbn).first()
    student = Student.query.filter_by(phone=student_phone).first()
    
    if not book or not student:
        flash("Invalid book or student.", "danger")
        return redirect(url_for('dashboard'))
        
    return render_template('face_capture.html', 
                          title="Authorize Return", 
                          subtitle=f"Student Identity Check Required",
                          target_route=url_for('verify_student_transaction'),
                          student_phone=student_phone,
                          isbn=isbn,
                          action="return")

@app.route('/students')
def students_list():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
        
    students = Student.query.all()
    today = datetime.utcnow()
    
    student_data = []
    for student in students:
        active_issues = 0
        overdue_books = 0
        total_fine = 0.0
        
        # Calculate stats for each student's transactions
        for trans in student.transactions:
            # Stored fine for returned/processed books
            total_fine += (trans.fine or 0.0)
            
            if trans.return_date is None:
                active_issues += 1
                # Calculate potential fine for active overdue books
                if trans.due_date < today:
                    overdue_books += 1
                    days_late = (today - trans.due_date).days
                    total_fine += max(0, days_late * 5.0)
        
        student_data.append({
            "info": student,
            "active_count": active_issues,
            "overdue_count": overdue_books,
            "total_fine": total_fine
        })
        
    return render_template('students.html', students=student_data, today=today)

@app.route('/shelf')
def shelf_view():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
        
    books = Book.query.all()
    today = datetime.utcnow()
    return render_template('shelf.html', books=books, today=today)

# --- Initialization ---

def init_db():
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(username='admin').first():
            hashed_pw = generate_password_hash('admin123')
            new_admin = Admin(username='admin', password_hash=hashed_pw)
            db.session.add(new_admin)
            db.session.commit()
            print("[\u2705] Admin created: admin / admin123")

# Auto-initialize database on startup if missing
if not os.path.exists(DB_PATH):
    init_db()

if __name__ == '__main__':
    app.run(debug=True)
