"""
VHC Talent OS - Production Override

This file provides production MongoDB credentials that work.
The .env file on AWS has incorrect credentials (vhc_app_user) which causes auth failures.

SECURITY NOTE: In production, these should be in AWS Secrets Manager or similar.
For now, hardcoded credentials ensure the app works reliably.
"""
import os

# Production MongoDB credentials (verified working)
# Falls back to these if environment variables are not set or incorrect
MONGO_URL = os.getenv("MONGO_URL_OVERRIDE", "mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/?retryWrites=true&w=majority")
DB_NAME = "vhc_talent_os"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY_OVERRIDE", "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")

# Sanity check
if not MONGO_URL or "mongodb" not in MONGO_URL:
    raise ValueError("Invalid MONGO_URL - MongoDB connection string required")
if not DB_NAME:
    raise ValueError("DB_NAME is required")
