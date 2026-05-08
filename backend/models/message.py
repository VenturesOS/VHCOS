"""
Message Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional


class MessageBase(BaseModel):
    recipient_id: str
    subject: str
    content: str


class MessageCreate(MessageBase):
    pass


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    sender_id: str
    sender_name: Optional[str] = None
    recipient_id: str
    recipient_name: Optional[str] = None
    subject: str
    content: str
    is_read: bool = False
    created_at: str
