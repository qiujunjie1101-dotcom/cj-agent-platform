from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_schema import Response
from src.infra.database import get_db_session
from src.modules.user.schema import UserCreate, UserRead
from src.modules.user.service import UserService


router = APIRouter(prefix="/user", tags=["user"])


def get_user_service(db: AsyncSession = Depends(get_db_session)) -> UserService:
    return UserService(db)


@router.post("/create", response_model=Response[UserRead])
async def create_user(
    data: UserCreate,
    service: UserService = Depends(get_user_service),
) -> Response[UserRead]:
    user = await service.create_user(data)
    return Response(code=0, msg="ok", data=UserRead.model_validate(user))

