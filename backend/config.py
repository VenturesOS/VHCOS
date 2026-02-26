"""
VHC Talent OS - Configuration Module
Handles environment variables, database connection, and R2 storage client.

FIXED:
- MongoDB URI loaded from environment variable (MONGODB_URI)
- Hardcoded credentials removed
- tlsInsecure removed (was disabling TLS certificate validation)
- Startup raises RuntimeError if MONGODB_URI is not set
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
load_dotenv(ROOT_DIR / ".env", override=True)

# ============== MONGODB CONNECTION ==============
mongodb_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL") or os.environ.get("MONGO_URL")
if not mongodb_uri:
    raise RuntimeError(
        "MONGODB_URI (or MONGO_URL) environment variable is not set. "
        "Add it to your .env file or deployment environment. "
        "Example: MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/dbname"
    )

db_name = os.environ.get("DB_NAME") or os.environ.get("MONGODB_DB_NAME", "vhc_talent_os")

client = AsyncIOMotorClient(
    mongodb_uri,
    maxPoolSize=10,
    minPoolSize=1,
    maxIdleTimeMS=30000,
    waitQueueTimeoutMS=15000,
    serverSelectionTimeoutMS=15000,
    connectTimeoutMS=10000,
    socketTimeoutMS=30000,
    retryWrites=True,
    retryReads=True,
    maxConnecting=2,
    tls=True,
    tlsCAFile=certifi.where(),
    # NOTE: tlsInsecure is intentionally NOT set.
    # It was previously set to True, which disabled TLS certificate validation
    # and made the connection vulnerable to man-in-the-middle attacks.
)

db = client[db_name]

# Startup diagnostics (masked)
import warnings
_masked_uri = mongodb_uri[:20] + "***" + mongodb_uri[-30:] if len(mongodb_uri) > 50 else "***"
warnings.warn(f"\n{'='*60}\n  VHC TALENT OS — ENVIRONMENT REPORT\n  DB           = {db_name}\n  MONGO_SOURCE = env\n{'='*60}")
warnings.warn(f"{'='*60}\n  MONGO CONNECTION DIAGNOSTICS\n  ACTUAL URI    = {_masked_uri}\n  DB_NAME (used)= {db_name}\n{'='*60}")
logging.info(f"MongoDB client initialized. DB: {db_name}")

# ============== CLOUDFLARE R2 STORAGE ==============
R2_ACCOUNT_ID      = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID   = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME     = os.environ.get("R2_BUCKET_NAME", "vhc-talent-os-storage")
R2_ENDPOINT        = os.environ.get("R2_ENDPOINT")

r2_client = None
R2_ENABLED = False

if R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY:
    try:
        r2_endpoint = R2_ENDPOINT or f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        r2_client = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
            region_name="auto",
        )
        R2_ENABLED = True
        logging.info(f"Cloudflare R2 client initialized. Bucket: {R2_BUCKET_NAME}")
    except Exception as e:
        logging.warning(f"Cloudflare R2 initialization failed: {e}. Using local storage fallback.")
        R2_ENABLED = False
else:
    logging.info("Cloudflare R2 credentials not configured. Using local storage.")

# ============== JWT CONFIGURATION ==============
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    logging.warning(
        "JWT_SECRET_KEY not set in environment — using insecure default. "
        "Set JWT_SECRET_KEY in production."
    )
    JWT_SECRET_KEY = "vhc-secret-key-CHANGE-IN-PRODUCTION"

JWT_ALGORITHM              = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# ============== FILE UPLOAD CONFIGURATION ==============
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

PARENT_UPLOAD_DIR = ROOT_DIR.parent / "uploads"
PARENT_UPLOAD_DIR.mkdir(exist_ok=True)

# ============== SERVICES INITIALIZATION ==============

def init_services():
    """Initialize services that require DB connection."""
    try:
        from services.job_queue import job_queue
        job_queue.set_db(db)
        logging.info("Job queue service initialized with DB")
    except Exception as e:
        logging.warning(f"Job queue service initialization failed: {e}")


init_services()
