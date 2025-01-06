import os
import base64
from google.cloud import bigquery
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.auth.exceptions import RefreshError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google_auth_oauthlib.flow import InstalledAppFlow
from config import Config  # Importing config for credentials

# Set up the path to your service account JSON file
credentials_path = Config.ADMIN_SDK_CREDENTIALS  # Path to your service account key

# BigQuery setup
credentials = service_account.Credentials.from_service_account_file(credentials_path)
client = bigquery.Client(credentials=credentials)

# Gmail API setup
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    """Get Gmail service using OAuth2"""
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    # It is created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        creds = service_account.Credentials.from_service_account_file(credentials_path)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            try:
                # Make sure to load your Gmail API credentials from your config file
                flow = InstalledAppFlow.from_client_secrets_file(
                    Config.GMAIL_API_CREDENTIALS,
                    SCOPES
                )
                creds = flow.run_local_server(port=5000, redirect_uri='http://localhost:5000/oauth2callback')
                # Save the credentials for the next run
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                print(f"Error during authentication: {str(e)}")
                return None
    return build('gmail', 'v1', credentials=creds)

def send_emails(request):
    """Send emails to students whose email_sent is FALSE"""
    try:
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            raise Exception("Failed to authenticate with Gmail API")

        # Query BigQuery to get student data
        query = """
            SELECT personal_email, first_name, last_name
            FROM `project_id.dataset.table`
            WHERE email_sent = FALSE
        """
        query_job = client.query(query)
        rows = query_job.result()

        if not rows:
            return "No emails to send.", 200

        # Send emails to each student
        for row in rows:
            email = row['personal_email']
            name = f"{row['first_name']} {row['last_name']}"
            subject = "Welcome to the University!"
            body = f"Hi {name},\n\nYour university email has been created.\n\nBest regards,\nUniversity Admin"

            # Create the email message
            message = create_message('your_email@gmail.com', email, subject, body)

            # Send the message via Gmail API
            send_message(service, 'me', message)

        # After sending the emails, mark them as sent in BigQuery
        update_query = """
            UPDATE `project_id.dataset.table`
            SET email_sent = TRUE
            WHERE email_sent = FALSE
        """
        client.query(update_query)

        return "Emails sent successfully!", 200
    except Exception as e:
        return f"Error: {str(e)}", 500

def create_message(sender, to, subject, body):
    """Create an email message to send via Gmail API"""
    message = MIMEMultipart()
    message['to'] = to
    message['subject'] = subject
    message.attach(MIMEText(body, 'plain'))
    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}

def send_message(service, user_id, message):
    """Send the email via Gmail API"""
    try:
        message = service.users().messages().send(userId=user_id, body=message).execute()
        print(f"Message sent: {message['id']}")
    except Exception as e:
        print(f"Failed to send message: {str(e)}")
