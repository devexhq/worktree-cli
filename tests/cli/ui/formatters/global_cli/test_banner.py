"""Tier 2 presentation contract tests for WelcomeBannerFormatter."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.events import WelcomeBannerEvent
from worktree.cli.ui.formatters.global_cli.banner import WelcomeBannerFormatter

STANDARD_VERSION = FormatterCase(
    data=WelcomeBannerEvent(version="0.1.0"),
    view=WelcomeBannerEvent(version="0.1.0"),
    render_expectations=["v0.1.0"],
)

PRERELEASE_VERSION = FormatterCase(
    data=WelcomeBannerEvent(version="1.2.3-rc.1"),
    view=WelcomeBannerEvent(version="1.2.3-rc.1"),
    render_expectations=["v1.2.3-rc.1"],
)

BANNER_CASES = [
    pytest.param(STANDARD_VERSION, id="standard_version"),
    pytest.param(PRERELEASE_VERSION, id="prerelease_version"),
]

BANNER_PAYLOAD_CASES = [
    pytest.param(STANDARD_VERSION, {"version": "0.1.0"}, id="standard_version"),
    pytest.param(PRERELEASE_VERSION, {"version": "1.2.3-rc.1"}, id="prerelease_version"),
]


class WelcomeBannerFormatterTests:
    """Tier 2 presentation contract tests for WelcomeBannerFormatter."""

    @pytest.mark.parametrize("case", BANNER_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[WelcomeBannerEvent, WelcomeBannerEvent]) -> None:
        """Verify transform returns the identity view representation."""
        assert WelcomeBannerFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), BANNER_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[WelcomeBannerEvent, WelcomeBannerEvent],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert WelcomeBannerFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", BANNER_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[WelcomeBannerEvent, WelcomeBannerEvent]
    ) -> None:
        """Verify non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(WelcomeBannerFormatter().to_rich(case.data))
        for expected in case.render_expectations:
            assert expected in rendered
