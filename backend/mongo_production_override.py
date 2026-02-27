"""
VHC Talent OS - Production MongoDB Override

This file forces connection to the external Atlas cluster instead of
the Emergent platform-managed MongoDB. Python files are guaranteed
to be deployed (unlike .conf or .env which the platform may overwrite).

TEMP OVERRIDE — remove once platform supports external MongoDB config.
"""

MONGO_URL = "mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "vhc_talent_os"
