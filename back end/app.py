import os
import csv
import smtplib
from flask import Flask, request, render_template, redirect, url_for, flash
from google.cloud import bigquery
from google.oauth2 import service_account
import time  # For retry mechanism
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config
import tempfile  # To handle temporary files

# Initialize Flask App
app = Flask(__name__)

# Configurations: Import from Config class
app.config.from_object(Config)

# Initialize BigQuery Client
credentials = service_account.Credentials.from_service_account_file(app.config['ADMIN_SDK_CREDENTIALS'])
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

# BigQuery Table ID
dataset_id = 'gcp'  # Replace with your dataset ID
table_id = 'students'  # Replace with your table ID

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465  # Using SSL port 465
FROM_EMAIL = "hushhush1807@gmail.com"
EMAIL_PASSWORD = "qacm kxbi elue rlbl"  # Use environment variables or a config file for security

# Helper: Check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Helper: Retry BigQuery Update with Buffer Status Check
def retry_update(query, max_retries=10, delay=60):
    for attempt in range(max_retries):
        try:
            client.query(query).result()  # Execute the update query
            return
        except Exception as e:
            if "streaming buffer" in str(e).lower() and attempt < max_retries - 1:
                print(f"Retrying due to streaming buffer: Attempt {attempt + 1}")
                time.sleep(delay)
                table_ref = client.dataset(dataset_id).table(table_id)
                table = client.get_table(table_ref)  # Fetch the table schema
                if table.streaming_buffer is not None:
                    print(f"Streaming buffer is still active, retrying...")
                    time.sleep(delay)
                else:
                    print(f"Streaming buffer cleared, proceeding with update.")
                    break
            else:
                raise e

# Route: Upload CSV and process it
@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        flash("No file selected!", "danger")
        return redirect(url_for('index'))

    file = request.files['file']

    if file.filename == '':
        flash("No file selected!", "danger")
        return redirect(url_for('index'))

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload a .csv file.", "danger")
        return redirect(url_for('index'))

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(filepath)

    try:
        process_csv(filepath)
        flash("File uploaded and processed successfully!", "success")
    except Exception as e:
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('index'))

# Process the uploaded CSV file
def process_csv(filepath):
    temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', newline='')

    fieldnames = ['first_name', 'last_name', 'personal_email', 'university_email', 'account_status', 'email_sent']

    with open(filepath, 'r') as file, temp_file:
        csv_data = csv.DictReader(file)
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()  # Write the header to the CSV file

        for row in csv_data:
            first_name = row['first_name'].strip().lower()
            last_name = row['last_name'].strip().lower()
            personal_email = row['personal_email'].strip()

            university_email = f"{first_name}.{last_name}@srh.com"
            writer.writerow({
                "first_name": first_name.capitalize(),
                "last_name": last_name.capitalize(),
                "personal_email": personal_email,
                "university_email": university_email,
                "account_status": "Active",
                "email_sent": False  # New column to track email status
            })

    try:
        staging_table_ref = client.dataset(dataset_id).table('students_staging')

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,  # Skip the header row
            autodetect=True  # Automatically detect the schema based on the CSV content
        )

        with open(temp_file.name, 'rb') as f:
            load_job = client.load_table_from_file(f, staging_table_ref, job_config=job_config)
        load_job.result()

        print(f"Data successfully loaded into staging table")

        transfer_data_query = f"""
            INSERT INTO `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students` (first_name, last_name, personal_email, university_email, account_status, email_sent)
            SELECT first_name, last_name, personal_email, university_email, account_status, email_sent
            FROM `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students_staging`
        """
        client.query(transfer_data_query).result()
        print("Data successfully transferred to main table")

    except Exception as e:
        raise Exception(f"Error loading data into BigQuery: {e}")
    finally:
        os.remove(temp_file.name)

# Function: Send Email
def send_email(to_email, subject, message):
    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(FROM_EMAIL, EMAIL_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)

# Route: Trigger Email Sending
@app.route('/send_email', methods=['POST'])
def send_emails():
    query = f"""
        SELECT first_name, last_name, personal_email, university_email
        FROM `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students`
        WHERE email_sent = FALSE
    """
    try:
        query_job = client.query(query)
        results = query_job.result()

        if results.total_rows == 0:
            flash("No new students to email.", "info")
            return redirect(url_for('index'))

        for row in results:
            subject = "Welcome to the University!"
            message = (f"Hi {row['first_name']} {row['last_name']},\n\n"
                       f"Your university account has been created.\n"
                       f"University Email: {row['university_email']}\n\n"
                       f"Best regards,\nUniversity Admin")

            success, response = send_email(row['personal_email'], subject, message)
            if not success:
                flash(f"Failed to send email to {row['personal_email']}: {response}", "danger")
                continue

        update_query = f"""
            UPDATE `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students`
            SET email_sent = TRUE
            WHERE email_sent = FALSE
        """
        time.sleep(60)
        retry_update(update_query)
        flash("Emails sent successfully to new students!", "success")
    except Exception as e:
        flash(f"An error occurred while sending emails: {e}", "danger")

    return redirect(url_for('index'))

# Route: Delete Records (Handle Deletion)
@app.route('/delete_records', methods=['POST'])
def delete_records():
    try:
        delete_all = 'delete_all' in request.form  # Check if the "Delete All" checkbox is checked
        selected_emails = request.form.getlist('selected_emails')  # Get selected emails

        # Check if either delete_all or selected_emails are provided
        if delete_all:
            # Delete all records from the table
            delete_query = f"""
                DELETE FROM `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students`
            """
            client.query(delete_query).result()
            flash("All student records have been deleted successfully!", "success")

        elif selected_emails:
            # Delete selected records from the table
            email_placeholders = ', '.join([f"'{email}'" for email in selected_emails])
            delete_query = f"""
                DELETE FROM `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students`
                WHERE personal_email IN ({email_placeholders})
            """
            client.query(delete_query).result()
            flash(f"Selected records have been deleted successfully!", "success")

        else:
            flash("No records selected for deletion.", "danger")

    except Exception as e:
        flash(f"An error occurred while deleting records: {e}", "danger")

    return redirect(url_for('index'))

# Route: Show Students to Delete
@app.route('/delete_students')
def delete_students():
    try:
        query = f"SELECT * FROM `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students`"
        query_job = client.query(query)
        students = [dict(row) for row in query_job.result()]
    except Exception as e:
        students = []
        flash(f"An error occurred while fetching student data: {e}", "danger")

    return render_template('delete_students.html', students=students)

# Route: Index Page
@app.route('/')
def index():
    try:
        query = f"SELECT * FROM `{Config.GOOGLE_CLOUD_PROJECT}.gcp.students`"
        query_job = client.query(query)
        students = [dict(row) for row in query_job.result()]
    except Exception as e:
        students = []
        flash(f"An error occurred while fetching student data: {e}", "danger")

    return render_template('index.html', students=students)

# Run Flask App
if __name__ == '__main__':
    app.run(debug=True, port=5000)
