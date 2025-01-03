from flask import Flask, request, jsonify
import csv
from google.cloud import bigquery
from google.oauth2 import service_account
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging


logging.basicConfig(level=logging.DEBUG)


# Initialize Flask App
app = Flask(__name__)

# BigQuery Configuration
JSON_KEY_PATH = "/Users/vedanth/Downloads/case-study-446714-47a6b51ba58a.json"  # Replace with your JSON key file path
credentials = service_account.Credentials.from_service_account_file(JSON_KEY_PATH)
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

# BigQuery Table ID
table_id = "case-study-446714.gcp.students"  # Replace with your BigQuery table ID

# Gmail SMTP Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "hushhush1807@gmail.com"  # Replace with your Gmail address
EMAIL_PASSWORD = "whej odqr tmop gejc"  # Replace with your Gmail password or App Password


@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    try:
        file = request.files['file']
        csv_data = csv.DictReader(file.stream)

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

        # Insert data into BigQuery
        errors = client.insert_rows_json(table_id, rows_to_insert)
        if errors:
            return jsonify({"error": f"Failed to upload some rows: {errors}"}), 500

        return jsonify({"message": "Students data uploaded and university emails generated successfully!"})

    except Exception as e:
        print(f"Error uploading CSV: {e}")
        return jsonify({"error": "An error occurred while uploading the CSV!"}), 500


@app.route('/get_students', methods=['GET'])
def get_students():
    try:
        query = f"SELECT * FROM `{table_id}`"
        results = client.query(query).result()

        students = [dict(row) for row in results]
        return jsonify(students)
    except Exception as e:
        print(f"Error fetching students: {e}")
        return jsonify({"error": "An error occurred while fetching students!"}), 500


@app.route('/delete_account', methods=['POST'])
def delete_account():
    try:
        data = request.json
        email = data['email']

        # Delete the student record by university email
        query = f"""
        DELETE FROM `{table_id}`
        WHERE university_email = @university_email
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("university_email", "STRING", email)]
        )
        client.query(query, job_config=job_config).result()

        return jsonify({"message": f"Account {email} deleted successfully!"})

    except Exception as e:
        print(f"Error deleting account: {e}")
        return jsonify({"error": "An error occurred while deleting the account!"}), 500


@app.route('/send_emails', methods=['POST'])
def send_emails():
    try:
        query = f"SELECT * FROM `{table_id}` WHERE account_status = 'Active'"
        results = client.query(query).result()

        students = [dict(row) for row in results]

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

            for student in students:
                subject = "Your University Email"
                body = f"""
                Hi {student['first_name']},

                Your university email has been created successfully:
                {student['university_email']}

                Regards,
                University Admin
                """

                msg = MIMEMultipart()
                msg['From'] = EMAIL_ADDRESS
                msg['To'] = student['personal_email']
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain'))

                server.sendmail(EMAIL_ADDRESS, student['personal_email'], msg.as_string())

        return jsonify({"message": "Emails sent successfully!"})

    except Exception as e:
        print(f"Error sending emails: {e}")
        return jsonify({"error": "An error occurred while sending emails!"}), 500


if __name__ == '__main__':
    app.run(debug=True)
