from collections.abc import Sequence

from pydantic import EmailStr

from src.core.base_repository import BaseRepository
from src.modules.user.model import User


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        return await self.get_by(username=username)

    async def get_by_email(self, email: EmailStr) -> User | None:
        return await self.get_by(email=str(email))

    async def get_all(self, offset: int = 0, limit: int = 10) -> Sequence[User]:
        return await self.list(offset=offset, limit=limit, order_by="id")
