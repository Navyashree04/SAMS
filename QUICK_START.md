# 🚀 SAMS - Quick Start Guide

## Getting Started in 3 Steps

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```
Or use the included run script (Linux/Mac):
```bash
./run.sh
```

### Step 2: Start the Application
```bash
python app.py
```

### Step 3: Open Your Browser
Navigate to: **http://localhost:5000**

## 🔐 Login Credentials

| Role | Username | Password |
|------|----------|----------|
| **Admin** | admin | admin123 |
| **Faculty** | faculty1 | faculty123 |
| **Student** | student1 | student123 |

## 📚 User Guides

### For Admins
1. **Add Users**: Click "Users" → "Add New User"
2. **Create Courses**: Click "Courses" → "Add New Course"
3. **Setup Classes**: Click "Classes" → "Add New Class"
4. **View Reports**: Click "Reports" → "Attendance Report"

### For Faculty
1. **Create Session**: Click "New Session" → Fill form → Submit
2. **Generate QR Code**: Open session → QR code displays automatically
3. **Mark Attendance**: Click on session → Mark students as Present/Absent
4. **Export Reports**: Go to "Reports" → Select class → Export CSV/PDF

### For Students
1. **View Attendance**: Click "My Attendance" → Select course
2. **Scan QR Code**: Click "Scan QR" → Enter QR code → Submit
3. **Check Notifications**: Click "Notifications" to see alerts

## 🎯 Key Features

### Admin Dashboard
- 📊 Statistics overview
- 👥 User management
- 📖 Course & class management
- 📈 Comprehensive reports

### Faculty Dashboard
- 📝 Create attendance sessions
- 🎫 Generate QR codes
- ✅ Manual attendance marking
- 📄 Export reports (CSV, PDF)

### Student Dashboard
- 📊 Attendance summary
- 📱 QR code scanning
- 📧 Notifications
- 📈 Detailed history

## 🔧 Troubleshooting

### Port Already in Use
```bash
# Edit app.py and change the port
app.run(debug=True, host='0.0.0.0', port=5001)
```

### Database Issues
```bash
# Delete and recreate database
rm sams.db
python app.py
```

### Template Not Found
- Ensure templates/ folder exists
- Check file permissions

## 📝 Common Tasks

### Add a New Student
1. Login as **admin**
2. Go to **Users** → **Add New User**
3. Fill in details:
   - Username, Email, Password
   - Role: **Student**
   - Student ID, Department, Year, Section
4. Click **Create User**

### Create Attendance Session
1. Login as **faculty**
2. Go to **New Session**
3. Select:
   - Class
   - Date
   - Start & End Time
4. Click **Create Session**
5. Share QR code with students

### Mark Attendance via QR
1. Login as **student**
2. Click **Scan QR**
3. Enter QR code from faculty
4. Click **Submit**
5. Attendance marked! ✅

## 📧 Email Notifications

To enable email notifications:

1. Open `app.py`
2. Find the `send_email()` function
3. Update SMTP settings:
```python
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "your_email@gmail.com"
SMTP_PASSWORD = "your_app_password"
```
4. Uncomment the email sending code
5. Restart the application

## 🎨 Customization

### Change Theme Colors
Edit `static/css/style.css`:
```css
.bg-primary { background: your-color !important; }
```

### Modify Attendance Threshold
Edit `app.py`:
```python
if percentage < 75:  # Change 75 to your threshold
    # Send notification
```

## 📱 Mobile Access

The application is responsive and works on:
- ✅ Desktop browsers
- ✅ Tablets
- ✅ Mobile phones

## 🔒 Security Notes

- ⚠️ Change default passwords in production
- ⚠️ Use HTTPS in production
- ⚠️ Set `debug=False` for production
- ⚠️ Configure proper email credentials
- ⚠️ Use strong passwords

## 💡 Tips & Tricks

1. **Bulk Operations**: Use CSV import for adding multiple students (feature can be added)
2. **Backup Database**: Regularly backup `sams.db` file
3. **Session Timeout**: Sessions expire after 30 minutes of inactivity
4. **QR Code Expiry**: QR codes expire after 1 hour for security
5. **Low Attendance Alert**: Automatic notification when attendance < 75%

## 🆘 Need Help?

Common questions:

**Q: Can I change the attendance threshold?**
A: Yes, edit line in `app.py` where `percentage < 75`

**Q: How to export all data?**
A: Use the CSV export feature in Reports section

**Q: Can multiple faculty teach same course?**
A: Yes, create separate classes for each faculty-course combination

**Q: How to reset a user's password?**
A: Admin can delete and recreate the user

## 📊 Understanding Reports

### Attendance Percentage Calculation
```
Percentage = (Present + Late) / Total Sessions × 100
```

### Status Indicators
- 🟢 Green (≥75%): Good attendance
- 🟡 Yellow (60-74%): Warning
- 🔴 Red (<60%): Critical

## 🎓 Educational Use

This project was developed as part of:
- **Software Engineering Course**
- **Database Management Course**
- **Web Development Course**

Based on official SRS and SAD documents.

## ⚡ Performance Tips

For better performance:
1. Index frequently queried columns
2. Use PostgreSQL for production
3. Enable caching
4. Optimize queries
5. Use CDN for static files

## 🌟 Future Enhancements

Potential additions:
- 📱 Mobile app (React Native)
- 🔐 OAuth login (Google, Microsoft)
- 📊 Advanced analytics
- 🎯 Biometric attendance
- 📅 Calendar integration
- 💬 Chat support
- 📝 Assignment management

---

**Happy Attendance Tracking! 📚✨**

For issues or questions, refer to the full README.md