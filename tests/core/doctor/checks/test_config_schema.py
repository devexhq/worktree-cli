"""Unit tests for worktree.core.doctor.checks.config_schema."""

from pathlib import Path

from tests.harness import assert_model_equal
from worktree.common.filesystem import Filesystem
from worktree.core.config.generator import build_default_config
from worktree.core.doctor.checks.config_schema import ConfigSchemaCheck
from worktree.core.doctor.models import CheckCategory, CheckStatus, DiagnosticCheckResult, DoctorContext


class ConfigSchemaCheckTests:
    """Unit tests for ConfigSchemaCheck diagnostic outcomes."""

    def test_execute_missing_config_file_returns_not_found_failure(self, isolated_workspace: Path) -> None:
        """[tier-1/unit] ConfigSchemaCheck.execute: no .worktree/config.json -> FAILED with DOCTOR_CONFIG_NOT_FOUND."""
        check = ConfigSchemaCheck()
        context = DoctorContext(cwd=isolated_workspace)

        result = check.execute(context)

        config_path = isolated_workspace / ".worktree" / "config.json"
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="config.schema",
                name="Config Schema Check",
                category=CheckCategory.CONFIG,
                status=CheckStatus.FAILED,
                message=f"Configuration file not found at '{config_path}' (CONFIG_NOT_FOUND).",
                details={},
                duration_ms=0.0,
                error_code="DOCTOR_CONFIG_NOT_FOUND",
                errors=[f"Configuration file not found at '{config_path}' (CONFIG_NOT_FOUND)."],
                warnings=[],
                fixes=["Run `wt init` to create `.worktree/config.json`"],
            ),
        )

    def test_execute_malformed_json_returns_malformed_failure(self, isolated_workspace: Path) -> None:
        """[tier-1/unit] ConfigSchemaCheck.execute: invalid JSON syntax -> FAILED with DOCTOR_CONFIG_MALFORMED."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        config_path.write_text("{not valid json", encoding="utf-8")
        check = ConfigSchemaCheck()
        context = DoctorContext(cwd=isolated_workspace)

        result = check.execute(context)

        message = (
            f"Malformed config.json at '{config_path}': "
            "Expecting property name enclosed in double quotes at line 1 column 2 (char 1) "
            "(CONFIG_MALFORMED_JSON)."
        )
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="config.schema",
                name="Config Schema Check",
                category=CheckCategory.CONFIG,
                status=CheckStatus.FAILED,
                message=message,
                details={},
                duration_ms=0.0,
                error_code="DOCTOR_CONFIG_MALFORMED",
                errors=[message],
                warnings=[],
                fixes=["Repair JSON syntax, or restore from backup"],
            ),
        )

    def test_execute_schema_invalid_payload_returns_schema_invalid_failure(self, isolated_workspace: Path) -> None:
        """[tier-1/unit] ConfigSchemaCheck.execute: valid JSON missing required sections -> FAILED with DOCTOR_CONFIG_SCHEMA_INVALID."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        Filesystem.atomic_write_json(config_path, {})
        check = ConfigSchemaCheck()
        context = DoctorContext(cwd=isolated_workspace)

        result = check.execute(context)

        message = "\n".join(
            [
                "Config schema validation failed (CONFIG_SCHEMA_INVALID):",
                "- (root): 'version' is a required property",
                "- (root): 'project' is a required property",
                "- (root): 'paths' is a required property",
                "- (root): 'sandbox' is a required property",
                "- (root): 'agent' is a required property",
                "- (root): 'history' is a required property",
                "- (root): 'doctor' is a required property",
                "- (root): 'prune' is a required property",
                "- (root): 'telemetry' is a required property",
                "- (root): 'concurrency' is a required property",
            ]
        )
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="config.schema",
                name="Config Schema Check",
                category=CheckCategory.CONFIG,
                status=CheckStatus.FAILED,
                message=message,
                details={"schema_errors": [message]},
                duration_ms=0.0,
                error_code="DOCTOR_CONFIG_SCHEMA_INVALID",
                errors=[message],
                warnings=[],
                fixes=[
                    "Run `wt config validate` for details",
                    "Or `wt init --repair` to insert missing keys without overwriting values",
                ],
            ),
        )

    def test_execute_valid_config_returns_ok(self, isolated_workspace: Path) -> None:
        """[tier-1/unit] ConfigSchemaCheck.execute: schema-valid config.json -> OK with no errors."""
        config_path = isolated_workspace / ".worktree" / "config.json"
        Filesystem.atomic_write_json(config_path, build_default_config("demo-workspace"))
        check = ConfigSchemaCheck()
        context = DoctorContext(cwd=isolated_workspace)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="config.schema",
                name="Config Schema Check",
                category=CheckCategory.CONFIG,
                status=CheckStatus.OK,
                message="`.worktree/config.json` is present and passes schema V1 validation.",
                details={},
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
