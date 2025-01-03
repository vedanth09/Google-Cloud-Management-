import os
import csv
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from google.cloud import bigquery
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from config import Config

# Initialize Flask App
app = Flask(__name__)

# Configurations: Import from Config class
app.config.from_object(Config)

# Initialize BigQuery Client
credentials = service_account.Credentials.from_service_account_file(app.config['ADMIN_SDK_CREDENTIALS'])
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

# BigQuery Table ID
table_id = f"{Config.GOOGLE_CLOUD_PROJECT}.gcp.students"  # Replace with your table ID

# Gmail API Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Function to authenticate and create Gmail API service
def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = service_account.Credentials.from_service_account_file(app.config['GMAIL_API_CREDENTIALS'])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                app.config['GMAIL_API_CREDENTIALS'],
                SCOPES)
            # Using a fixed port for the redirect URI to avoid conflicts
            creds = flow.run_local_server(port=5000, redirect_uri='http://localhost:5000/oauth2callback')  # Set your redirect URI here
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

# Function to send email
def send_email(service, to, subject, body):
    message = MIMEMultipart()
    message['to'] = to
    message['subject'] = subject
    msg = MIMEText(body)
    message.attach(msg)
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    send_message = service.users().messages().send(userId="me", body={'raw': raw_message}).execute()
    return send_message

# Route: Send Email to All Students
@app.route('/send_email', methods=['POST'])
def send_bulk_email():
    try:
        # Get Gmail service
        service = get_gmail_service()

        # Retrieve all students' emails from BigQuery or your data
        query = f"SELECT personal_email, first_name, last_name FROM {Config.GOOGLE_CLOUD_PROJECT}.gcp.students"
        query_job = client.query(query)
        rows = query_job.result()

        for row in rows:
            student_email = row['personal_email']
            student_name = f"{row['first_name'].capitalize()} {row['last_name'].capitalize()}"
            subject = "Your University Email Has Been Created"
            body = f"Hi {student_name},\n\nYour university email has been created successfully.\nYour university email: {row['first_name'].lower()}.{row['last_name'].lower()}@srh.com\n\nBest regards,\nUniversity Admin"
            send_email(service, student_email, subject, body)

        flash("Emails sent successfully to all students!", "success")
    except Exception as e:
        print(f"An error occurred while sending emails: {e}")
        flash(f"An error occurred while sending emails: {e}", "error")
    
    return redirect(url_for('index'))

# Route: Index Page
@app.route('/')
def index():
    return render_template('index.html')

# Helper: Check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Upload CSV and process it
@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        flash("No file selected!", "error")
        return redirect(url_for('index'))

    file = request.files['file']

    if file.filename == '':
        flash("No file selected!", "error")
        return redirect(url_for('index'))

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload a .csv file.", "error")
        return redirect(url_for('index'))

    # Save the file to the uploads directory
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(filepath)

    try:
        process_csv(filepath)
        flash("File uploaded and processed successfully!", "success")
    except Exception as e:
        flash(f"An error occurred: {e}", "error")

    return redirect(url_for('index'))

# Process the uploaded CSV file
def process_csv(filepath):
    with open(filepath, 'r') as file:
        csv_data = csv.DictReader(file)
        rows_to_insert = []

        for row in csv_data:
            first_name = row['first_name'].strip().lower()
            last_name = row['last_name'].strip().lower()
            personal_email = row['personal_email'].strip()

            university_email = f"{first_name}.{last_name}@srh.com"
            rows_to_insert.append({
                "first_name": first_name.capitalize(),
                "last_name": last_name.capitalize(),
                "personal_email": personal_email,
                "university_email": university_email,
                "account_status": "Active",
            })

        # Insert rows into BigQuery
        errors = client.insert_rows_json(table_id, rows_to_insert)
        if errors:
            raise Exception(f"BigQuery insertion errors: {errors}")

# Run Flask App
if __name__ == '__main__':
    app.run(debug=True, port=5000)  # Use a fixed port for easier debugging