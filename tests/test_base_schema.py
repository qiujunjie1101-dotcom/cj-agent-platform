import unittest

from pydantic import BaseModel, ValidationError

from src.core.base_schema import Response


class User(BaseModel):
    id: int
    name: str


class ResponseTests(unittest.TestCase):
    def test_data_defaults_to_none(self) -> None:
        response = Response(code=0, msg="ok")

        self.assertIsNone(response.data)
        self.assertEqual(response.model_dump(), {"code": 0, "msg": "ok", "data": None})

    def test_required_fields_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            Response(msg="缺少 code")  # type: ignore[call-arg]

    def test_generic_parameter_parses_nested_model(self) -> None:
        response = Response[User](code=0, msg="ok", data={"id": 1, "name": "阿强"})

        self.assertIsInstance(response.data, User)
        self.assertEqual(response.data.name, "阿强")

    def test_generic_parameter_rejects_wrong_type(self) -> None:
        with self.assertRaises(ValidationError):
            Response[int](code=0, msg="ok", data="不是数字")

    def test_generic_parameter_serializes(self) -> None:
        response = Response[list[int]](code=0, msg="ok", data=[1, 2])

        self.assertEqual(response.model_dump(), {"code": 0, "msg": "ok", "data": [1, 2]})


if __name__ == "__main__":
    unittest.main()
