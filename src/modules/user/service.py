import hashlib
import secrets
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exception import ConflictError, NotFoundError
from src.modules.user.model import User
from src.modules.user.repository import UserRepository
from src.modules.user.schema import UserCreate


class UserService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def create_user(self, data: UserCreate) -> User:
        if await self.repo.get_by_username(data.username):
            raise ConflictError("用户名已存在")
        if await self.repo.get_by_email(data.email):
            raise ConflictError("邮箱已存在")

        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", data.password.encode(), salt.encode(), 600_000
        ).hex()
        return await self.repo.create(
            username=data.username,
            email=str(data.email),
            hashed_password=f"pbkdf2_sha256${salt}${password_hash}",
        )

    async def get_user_by_id(self, user_id: int) -> User:
        user = await self.repo.get(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        return user

    async def get_all_users(
        self, offset: int = 0, limit: int = 10
    ) -> Sequence[User]:
        return await self.repo.get_all(offset=offset, limit=limit)
