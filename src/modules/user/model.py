from src.core.base_model import BaseModel, TimestampMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class User(BaseModel, TimestampMixin):  
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(32),unique=True,index=True, comment="用户名")
    email: Mapped[str] = mapped_column(String(32),unique=True,index=True, comment="邮箱")
    hashed_password: Mapped[str] = mapped_column(String(255), comment="密码哈希")
    is_active: Mapped[bool] = mapped_column(default=True, comment="是否激活")
