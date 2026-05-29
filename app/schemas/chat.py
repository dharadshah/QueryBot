from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    role: Optional[str] = "guest"
    customer_id: Optional[int] = None


class ChatResponse(BaseModel):
    session_id: str
    question: str
    answer: str
    sql_generated: Optional[str] = None
    rows_returned: Optional[int] = None
    success: bool
    error: Optional[str] = None