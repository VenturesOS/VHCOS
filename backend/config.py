"""
VHC Talent OS - Configuration Module
Handles environment variables, database connection, and R2 storage client.
"""
import os
import logging
import certifi
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import boto3
from botocore.config import Config

# ============== ENVIRONMENT SETUP ==============
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

# ============== MONGODB CONNECTION ==============
mongodb_uri = os.environ.get('MONGO_URL') or os.environ.get('MONGODB_URI')
if not mongodb_uri:
    raise RuntimeError("MONGO_URL is required. Application cannot start without database connection.")

client = AsyncIOMotorClient(
    mongodb_uri,
    maxPoolSize=50,
    minPoolSize=5,
    maxIdleTimeMS=30000,
    waitQueueTimeoutMS=15000,
    serverSelectionTimeoutMS=15000,
    connectTimeoutMS=10000,
    socketTimeoutMS=30000,
    retryWrites=True,
    retryReads=True,
    maxConnecting=3,
    tls=True,
    tlsInsecure=True,
    tlsCAFile=certifi.where(),
)

db_name = os.environ.get('DB_NAME', 'vhc_talent_os')
db = client[db_name]

# ============== CLOUDFLARE R2 STORAGE ==============
R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', 'vhc-talent-os-storage')
R2_ENDPOINT = os.environ.get('R2_ENDPOINT')

# R2 client - only initialize if credentials are provided
r2_client = None
R2_ENABLED = False

if R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY:
    try:
        r2_endpoint = R2_ENDPOINT or f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        r2_client = boto3.client(
            's3',
            endpoint_url=r2_endpoint,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            ),
            region_name='auto'
        )
        R2_ENABLED = True
        logging.info(f"Cloudflare R2 client initialized. Bucket: {R2_BUCKET_NAME}")
    except Exception as e:
        logging.warning(f"Cloudflare R2 initialization failed: {e}. Using local storage fallback.")
        R2_ENABLED = False
else:
    logging.info("Cloudflare R2 credentials not configured. Using local storage.")

# ============== JWT CONFIGURATION ==============
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'vhc-secret-key')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get('ACCESS_TOKEN_EXPIRE_MINUTES', 30))

# ============== FILE UPLOAD CONFIGURATION ==============
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Also check parent uploads directory (for backward compatibility)
PARENT_UPLOAD_DIR = ROOT_DIR.parent / "uploads"
PARENT_UPLOAD_DIR.mkdir(exist_ok=True)

# ============== SERVICES INITIALIZATION ==============
# Initialize services that need DB connection
def init_services():
    """Initialize services that require DB connection."""
    try:
        from services.job_queue import job_queue
        job_queue.set_db(db)
        logging.info("✅ Job queue service initialized with DB")
    except Exception as e:
        logging.warning(f"⚠️ Job queue service initialization failed: {e}")

# Call initialization
init_services()
