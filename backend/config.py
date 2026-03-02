"""
VHC Talent OS - Configuration Module
Handles environment variables, database connection, and R2 storage client.

DEPLOYMENT-SAFE: MongoDB client is NOT created at import time.
A lazy proxy pattern is used so that all `from config import db` references
work transparently — the real AsyncIOMotorClient is created only when
initialize_db() is called from a background task after the server has bound
to its port.
"""
import os
import logging
import certifi
from pathlib import Path
from dotenv import load_dotenv
import boto3
from botocore.config import Config

# ============== ENVIRONMENT SETUP ==============
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=False)

# ============== MONGODB URI RESOLUTION (no network calls) ==============
# Priority: mongo_production_override.py > MONGO_URL env var
# The override file survives Emergent's .env overwrite during deployment.
_REQUIRED_CLUSTER = "cluster0.vuhdiod.mongodb.net"
_REQUIRED_DB = "vhc_talent_os"
_override_active = False

try:
    from mongo_production_override import MONGO_URL as _override_url, DB_NAME as _override_db
    if _override_url and _REQUIRED_CLUSTER in _override_url:
        mongodb_uri = _override_url
        db_name = _override_db or _REQUIRED_DB
        _override_active = True
        logging.info(f"[CONFIG] Using mongo_production_override.py (cluster: {_REQUIRED_CLUSTER})")
    # Always inject OPENAI_API_KEY from override file (Emergent overwrites .env with its own keys)
    try:
        from mongo_production_override import OPENAI_API_KEY as _override_oai_key
        if _override_oai_key:
            os.environ["OPENAI_API_KEY"] = _override_oai_key
            logging.info("[CONFIG] Injected OPENAI_API_KEY from override file (authoritative)")
    except (ImportError, AttributeError):
        pass
except Exception as e:
    logging.warning(f"[CONFIG] mongo_production_override.py failed: {e}")
    logging.info("[CONFIG] Falling back to env vars")

if not _override_active:
    _env_uri = os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL")
    if not _env_uri:
        raise RuntimeError(
            "MONGO_URL environment variable is not set and mongo_production_override.py "
            "is missing or invalid. Cannot start without a MongoDB connection."
        )
    mongodb_uri = _env_uri
    db_name = os.environ.get("DB_NAME", _REQUIRED_DB)

# Safety check: refuse to start if URI doesn't point to the correct Atlas cluster
if _REQUIRED_CLUSTER not in mongodb_uri:
    logging.warning(
        f"[CONFIG] WARNING: MongoDB URI does not contain '{_REQUIRED_CLUSTER}'. "
        f"URI points to: {mongodb_uri[:40]}... — this may be the wrong database!"
    )
if db_name != _REQUIRED_DB:
    logging.warning(
        f"[CONFIG] WARNING: DB_NAME is '{db_name}', expected '{_REQUIRED_DB}'"
    )

# Client options — computed once, used later by initialize_db()
_client_opts = dict(
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
)

if "mongodb+srv" in mongodb_uri or "mongodb.net" in mongodb_uri:
    _client_opts["tls"] = True
    _client_opts["tlsCAFile"] = certifi.where()


# ============== LAZY PROXY (deployment-safe) ==============
class _MongoProxy:
    """Forwards attribute/item access to a real Motor object set later via .set_target()."""
    __slots__ = ("_target",)

    def __init__(self):
        object.__setattr__(self, "_target", None)

    def set_target(self, target):
        object.__setattr__(self, "_target", target)

    def _get(self):
        t = object.__getattribute__(self, "_target")
        if t is None:
            raise RuntimeError("Database not initialized yet — initialize_db() has not been called")
        return t

    def __getattr__(self, name):
        return getattr(self._get(), name)

    def __getitem__(self, key):
        return self._get()[key]

    def __bool__(self):
        return object.__getattribute__(self, "_target") is not None

    def __repr__(self):
        t = object.__getattribute__(self, "_target")
        return f"<_MongoProxy target={t!r}>"


# Proxy objects — importable immediately, zero network cost
client = _MongoProxy()
db = _MongoProxy()


def initialize_db():
    """Create the real AsyncIOMotorClient and wire up the proxies.
    Call this ONCE from a background task after the server has bound to its port."""
    from motor.motor_asyncio import AsyncIOMotorClient

    real_client = AsyncIOMotorClient(mongodb_uri, **_client_opts)
    real_db = real_client[db_name]

    client.set_target(real_client)
    db.set_target(real_db)

    _masked = mongodb_uri[:20] + "***" + mongodb_uri[-30:] if len(mongodb_uri) > 50 else "***"
    _label = "[EMERGENCY OVERRIDE ACTIVE]" if _override_active else "[ENV-BASED CONFIG]"
    logging.warning(
        f"\n{'='*60}\n  {_label}\n  ACTUAL URI    = {_masked}\n"
        f"  DB_NAME       = {db_name}\n  MONGO_SOURCE  = "
        f"{'dotenv override' if _override_active else 'env var'}\n{'='*60}"
    )
    logging.info(f"MongoDB client initialized. DB: {db_name} | Override: {_override_active}")

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
    """Initialize services that require DB connection.
    Called from deferred_startup_tasks in server.py AFTER initialize_db()."""
    try:
        from services.job_queue import job_queue
        job_queue.set_db(db)
        logging.info("Job queue service initialized with DB")
    except Exception as e:
        logging.warning(f"Job queue service initialization failed: {e}")

# NOTE: init_services() is NOT called at module level.
# It is called from server.py's deferred startup task after the DB is initialized.
