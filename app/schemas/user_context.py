from pydantic import BaseModel
from typing import Optional
from app.constants.app_constants import UserRole


class UserContext(BaseModel):
    role: str = UserRole.GUEST
    customer_id: Optional[int] = None
    user_id: Optional[int] = None

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def is_customer(self) -> bool:
        return self.role == UserRole.CUSTOMER

    def is_guest(self) -> bool:
        return self.role == UserRole.GUEST