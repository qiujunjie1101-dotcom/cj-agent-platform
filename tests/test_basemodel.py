import unittest

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import BaseModel, SoftDeleteMixin, TimestampMixin


class User(BaseModel, TimestampMixin):
    __tablename__ = "users"

    nickname: Mapped[str] = mapped_column(String(32), comment="昵称")


class BaseModelTests(unittest.TestCase):
    def test_base_model_provides_autoincrement_primary_key(self) -> None:
        # BaseModel 自身不建表，只有子类才会被映射
        self.assertFalse(hasattr(BaseModel, "__table__"))
        self.assertIn("id", User.__table__.columns)
        self.assertTrue(User.__table__.c.id.primary_key)
        self.assertTrue(User.__table__.c.id.autoincrement)

    def test_timestamp_mixin_adds_both_timestamps(self) -> None:
        self.assertEqual(
            set(User.__table__.columns.keys()),
            {"id", "nickname", "created_at", "updated_at"},
        )
        self.assertFalse(User.__table__.c.created_at.primary_key)
        # 默认值必须落在服务器侧，否则手写 SQL 插入会因 NOT NULL 缺值报错
        self.assertIsNotNone(User.__table__.c.created_at.server_default)
        self.assertIsNotNone(User.__table__.c.updated_at.server_default)
        self.assertIsNotNone(User.__table__.c.updated_at.onupdate)

    def test_timestamp_mixin_is_reusable(self) -> None:
        class Agent(BaseModel, TimestampMixin):
            __tablename__ = "agents"

            name: Mapped[str] = mapped_column(String(64))

        self.assertIn("created_at", Agent.__table__.columns)
        self.assertIn("updated_at", Agent.__table__.columns)

    def test_soft_delete_mixin_adds_marker_columns(self) -> None:
        class Article(BaseModel, TimestampMixin, SoftDeleteMixin):
            __tablename__ = "articles"

            title: Mapped[str] = mapped_column(String(64))

        self.assertIn("is_deleted", Article.__table__.columns)
        self.assertIn("deleted_at", Article.__table__.columns)
        # 未删除是默认值，且默认值要落在数据库侧
        self.assertFalse(Article.__table__.c.is_deleted.nullable)
        self.assertIsNotNone(Article.__table__.c.is_deleted.server_default)
        # 未删除时 deleted_at 为空
        self.assertTrue(Article.__table__.c.deleted_at.nullable)

    def test_model_instantiates_with_keyword_arguments(self) -> None:
        user = User(nickname="cj")

        self.assertEqual(user.nickname, "cj")
        self.assertIsNone(user.id)


if __name__ == "__main__":
    unittest.main()
