import json
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel
from rich.text import Text

from tests.helpers import make_dispatcher_with_buffer
from worktree.cli.ui.dispatcher import UiDispatcher
from worktree.common.types import ComponentFormatter


class DummyItem(BaseModel):
    name: str
    count: int


@dataclass
class SimpleItem:
    value: str


class DummyItemFormatter(ComponentFormatter[DummyItem]):
    def to_rich(self, data: DummyItem) -> Text:
        style = self._STYLE_MAP.get("success", "green")
        return Text(f"Item: {data.name} ({data.count})", style=style)

    def to_json_serializable(self, data: DummyItem) -> dict[str, Any]:
        return data.model_dump(mode="json")


def test_dispatcher_direct_registration_instance() -> None:
    dispatcher, string_io = make_dispatcher_with_buffer()
    formatter = DummyItemFormatter()

    dispatcher.register(DummyItem, formatter)
    item = DummyItem(name="test", count=5)

    dispatcher.dispatch(item, output_format="terminal")
    assert "Item: test (5)" in string_io.getvalue()


def test_dispatcher_direct_registration_class() -> None:
    dispatcher, string_io = make_dispatcher_with_buffer()

    dispatcher.register(DummyItem, DummyItemFormatter)
    item = DummyItem(name="test2", count=10)

    dispatcher.dispatch(item, output_format="terminal")
    assert "Item: test2 (10)" in string_io.getvalue()


def test_dispatcher_decorator_registration() -> None:
    dispatcher, string_io = make_dispatcher_with_buffer()

    @dispatcher.register(SimpleItem)
    class DecItemFormatter(ComponentFormatter[SimpleItem]):
        def to_rich(self, data: SimpleItem) -> Text:
            return Text(f"Decorated: {data.value}")

        def to_json_serializable(self, data: SimpleItem) -> dict[str, Any]:
            return {"dec_value": data.value}

    item = SimpleItem(value="hello")
    dispatcher.dispatch(item, output_format="terminal")
    assert "Decorated: hello" in string_io.getvalue()


def test_dispatcher_json_ndjson_output(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    dispatcher.register(DummyItem, DummyItemFormatter())

    item = DummyItem(name="widget", count=42)
    dispatcher.dispatch(item, output_format="json")

    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed == {
        "event_type": "DummyItem",
        "payload": {"name": "widget", "count": 42},
    }


def test_dispatcher_unregistered_type_raises() -> None:
    dispatcher = UiDispatcher()
    with pytest.raises(ValueError, match="No formatter registered for type: DummyItem"):
        dispatcher.dispatch(DummyItem(name="unregistered", count=0))


def test_dispatcher_set_output_format(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    dispatcher.register(DummyItem, DummyItemFormatter())
    assert dispatcher.output_format == "terminal"

    dispatcher.set_output_format("json")
    assert dispatcher.output_format == "json"

    item = DummyItem(name="gear", count=1)
    dispatcher.dispatch(item)  # Omitting output_format uses active format ("json")

    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "DummyItem",
        "payload": {"name": "gear", "count": 1},
    }
