import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', '0b99bb08842bc3d6dda8bd3841057d54f9e73a3aac4da30d3395784f0c771ccc')
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'csv'}
    GOOGLE_CLOUD_PROJECT = 'case-study-446714'
    ADMIN_SDK_CREDENTIALS = '/Users/vedanth/Downloads/case-study-446714-305079e30e8c.json'
    GMAIL_API_CREDENTIALS = '/Users/vedanth/Downloads/client_secret_1031439173877-mmi7jgsm1i683292d5c8dc0vknsd846p.apps.googleusercontent.com (1).json'
