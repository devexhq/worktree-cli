"""Tests for the common package."""

from enum import StrEnum

from getworktree.common.utils import enum_value


class EnumObject(StrEnum):
    OK = "OK"
    NOT_OK = "NOT_OK"


class EnumLikeObject:
    @property
    def value(self):
        return "enum_like_object_value"


class CommonUtilsTests:
    """Tests for common utilities."""

    def test_enum_value_with_an_enum(self):
        value = enum_value(EnumObject.OK)
        assert value == "OK"

    def test_enum_value_with_an_enum_like_object(self):
        instance = EnumLikeObject()
        value = enum_value(instance)
        assert value == "enum_like_object_value"

    def test_enum_value_with_a_string(self):
        value = enum_value("my_value")
        assert value == "my_value"
