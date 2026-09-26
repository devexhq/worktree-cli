"""Contract tests for engine result and payload models."""

from __future__ import annotations

from worktree.core.engine.models import DefinitionRef, DefinitionsManifest, SessionRunPayload


class SessionRunPayloadDefinitionsTests:
    """Contract tests for SessionRunPayload.definitions round-tripping."""

    def test_session_run_payload_definitions_defaults_to_none(self) -> None:
        """SessionRunPayload: omitting definitions leaves it None, preserving a legacy run.json's round trip."""
        payload = SessionRunPayload(
            session_id="session-1",
            name="lint",
            status="completed",
            started_at="2026-01-01T00:00:00+00:00",
        )

        assert payload.definitions is None

    def test_session_run_payload_definitions_round_trips_through_json(self) -> None:
        """SessionRunPayload: a populated DefinitionsManifest survives model_dump_json/model_validate_json unchanged."""
        manifest = DefinitionsManifest(
            blueprint=DefinitionRef(
                ref="repo:blueprint:wt/my-blueprint",
                sha="a1b2c3d4",
                resolved_at="2026-09-25T19:04:00+00:00",
            ),
            steps=[
                DefinitionRef(
                    ref="repo:step:lint-check",
                    sha="e5f6a7b8",
                    resolved_at="2026-09-25T19:04:00+00:00",
                )
            ],
        )
        payload = SessionRunPayload(
            session_id="session-2",
            name="lint",
            status="completed",
            started_at="2026-01-01T00:00:00+00:00",
            definitions=manifest,
        )

        round_tripped = SessionRunPayload.model_validate_json(payload.model_dump_json())

        assert round_tripped == payload
        assert round_tripped.definitions == manifest
