# 📚 Library Management System (Flask)

A **professional offline Library Management System** built using Flask.
This system is designed for efficient book tracking, student management, and secure authentication using **Face Recognition** and **OCR-based ISBN scanning**.

---

## 🚀 Features

### 📊 Admin Dashboard

* Total Books, Available Books, Issued Books
* Overdue tracking
* Active transactions overview
* System status monitoring

### 📖 Book Management

* Add books manually (Title, Author, ISBN, Copies)
* Local SQLite database (offline system)
* ISBN-10 and ISBN-13 validation

### 🔄 Issue & Return System

* Issue books with student details
* Automatic due date (7 days)
* Return tracking with fine calculation (₹5/day)
* Real-time availability update

### 👨‍🎓 Student Management

* Track active issues
* View overdue books
* Fine tracking
* Transaction history with status badges

### 🔐 Face Recognition (Biometric Security)

* Admin login verification
* Student verification during issue/return
* Uses `face_recognition` with stored encodings

### 🔍 OCR-Based ISBN Scanner

* Scan ISBN using webcam
* Image processing with OpenCV
* Text extraction using pytesseract
* Supports ISBN-10 & ISBN-13

---

## 🛠 Tech Stack

| Technology       | Usage                    |
| ---------------- | ------------------------ |
| Python           | Backend                  |
| Flask            | Web framework            |
| SQLite           | Database (offline)       |
| OpenCV           | Image processing         |
| pytesseract      | OCR engine               |
| face_recognition | Biometric authentication |
| Bootstrap        | UI design                |

---

## 📦 Installation & Setup

### 1️⃣ Clone the repository

```bash
git clone https://github.com/your-username/library-management-system.git
cd library-management-system
```

---

### 2️⃣ Create virtual environment (optional but recommended)

```bash
python -m venv venv
source venv/bin/activate      # Linux / Mac
venv\Scripts\activate         # Windows
```

---

### 3️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Install Tesseract (IMPORTANT for OCR)

Download and install Tesseract:

* Windows: https://github.com/tesseract-ocr/tesseract
* After installation, verify:

```bash
tesseract --version
```

---

### 5️⃣ Run the application

```bash
python run.py
```

---

## 🌐 Application Routes

* `/login` → Admin login (Face verification)
* `/dashboard` → Main dashboard
* `/add-book` → Add new books
* `/process-isbn` → ISBN processing
* `/scan-isbn` → OCR scanner
* `/issue-book` → Issue book
* `/return-book` → Return book
* `/students` → Student management

---

## 📷 Screenshots

*Add your application screenshots here (Dashboard, Scanner, Face Login, etc.)*

---

## ⚠️ Important Notes

* This project is fully **offline** (No external APIs used)
* OCR accuracy may vary based on camera quality
* Face recognition requires proper lighting
* Database (`library.db`) is stored locally

---

## 🔮 Future Improvements

* Barcode scanner (more reliable than OCR)
* Role-based access (Admin / Librarian)
* Export reports (CSV / PDF)
* Advanced analytics dashboard
* Mobile responsive UI improvements

---

## 🤝 Contributing

Contributions are welcome!
Feel free to fork the repo and submit a pull request.

---

## 📄 License

This project is open-source and available under the MIT License.

---

## ⭐ Support

If you like this project, give it a ⭐ on GitHub!
