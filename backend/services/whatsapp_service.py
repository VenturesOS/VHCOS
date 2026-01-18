"""
WhatsApp Service for VHC Talent OS
Abstracted provider pattern (Twilio / Meta / future swap)
STRICT: Messages only sent with explicit user consent
"""
import os
import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Twilio Configuration (optional)
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', '')

# Check if WhatsApp is configured
WHATSAPP_ENABLED = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_NUMBER)

# Initialize Twilio client if configured
twilio_client = None
if WHATSAPP_ENABLED:
    try:
        from twilio.rest import Client
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("[WHATSAPP] Twilio client initialized")
    except Exception as e:
        logger.error(f"[WHATSAPP] Failed to initialize Twilio: {e}")
        WHATSAPP_ENABLED = False


def is_whatsapp_enabled() -> bool:
    """Check if WhatsApp service is configured and enabled"""
    return WHATSAPP_ENABLED


def validate_phone_number(phone: str) -> Optional[str]:
    """
    Validate and normalize phone number to E.164 format.
    Returns normalized number or None if invalid.
    """
    if not phone:
        return None
    
    # Remove all non-digit characters except leading +
    cleaned = ''.join(c for c in phone if c.isdigit() or c == '+')
    
    # Ensure starts with +
    if not cleaned.startswith('+'):
        # Assume India if 10 digits
        if len(cleaned) == 10:
            cleaned = '+91' + cleaned
        elif len(cleaned) == 11 and cleaned.startswith('0'):
            cleaned = '+91' + cleaned[1:]
        else:
            cleaned = '+' + cleaned
    
    # Validate length (E.164 is 8-15 digits after +)
    digits_only = cleaned.replace('+', '')
    if len(digits_only) < 8 or len(digits_only) > 15:
        return None
    
    return cleaned


async def send_whatsapp_message(
    recipient_phone: str,
    message_body: str,
    template_name: Optional[str] = None,
    template_variables: Optional[Dict] = None
) -> Dict:
    """
    Send WhatsApp message using Twilio.
    IMPORTANT: Only call this after verifying user consent!
    
    Args:
        recipient_phone: E.164 formatted phone number
        message_body: Message content (used for non-template messages)
        template_name: Optional approved template name
        template_variables: Variables for template
    
    Returns:
        Dict with status, message_sid, and details
    """
    if not WHATSAPP_ENABLED:
        logger.warning(f"[WHATSAPP] Service not configured. Would send to: {recipient_phone}")
        return {
            "status": "skipped",
            "message": "WhatsApp service not configured",
            "recipient": recipient_phone,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    # Validate phone number
    normalized_phone = validate_phone_number(recipient_phone)
    if not normalized_phone:
        logger.error(f"[WHATSAPP] Invalid phone number: {recipient_phone}")
        return {
            "status": "failed",
            "message": "Invalid phone number format",
            "recipient": recipient_phone,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    try:
        # Format for WhatsApp
        whatsapp_to = f"whatsapp:{normalized_phone}"
        whatsapp_from = f"whatsapp:{TWILIO_WHATSAPP_NUMBER}"
        
        # Send message (run sync in thread for non-blocking)
        def send_sync():
            return twilio_client.messages.create(
                from_=whatsapp_from,
                to=whatsapp_to,
                body=message_body
            )
        
        message = await asyncio.to_thread(send_sync)
        
        logger.info(f"[WHATSAPP] Sent to {normalized_phone}, SID: {message.sid}")
        return {
            "status": "sent",
            "message_sid": message.sid,
            "recipient": normalized_phone,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[WHATSAPP] Failed to send to {recipient_phone}: {str(e)}")
        return {
            "status": "failed",
            "message": str(e),
            "recipient": recipient_phone,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


async def send_batch_whatsapp(messages: List[Dict]) -> List[Dict]:
    """
    Send multiple WhatsApp messages concurrently.
    Each message dict should have: recipient_phone, message_body
    """
    tasks = [
        send_whatsapp_message(
            recipient_phone=msg["recipient_phone"],
            message_body=msg["message_body"],
            template_name=msg.get("template_name"),
            template_variables=msg.get("template_variables")
        )
        for msg in messages
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "status": "failed",
                "message": str(result),
                "recipient": messages[i]["recipient_phone"]
            })
        else:
            processed_results.append(result)
    
    return processed_results
