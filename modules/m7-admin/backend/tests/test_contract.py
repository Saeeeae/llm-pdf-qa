"""
B3.2 Schemathesis contract lock — M7 Admin Backend.

Validates that packages/contracts/m7-admin.openapi.yaml is internally consistent.
No live server required: static spec validation only.

Run:
  pytest modules/m7-admin/backend/tests/test_contract.py -v
"""

import pathlib
import pytest

CONTRACTS_DIR = pathlib.Path(__file__).parents[5] / "packages" / "contracts"
SPEC_PATH = CONTRACTS_DIR / "m7-admin.openapi.yaml"

try:
    import schemathesis
    SCHEMATHESIS_AVAILABLE = True
except ImportError:
    SCHEMATHESIS_AVAILABLE = False


@pytest.mark.skipif(not SCHEMATHESIS_AVAILABLE, reason="schemathesis not installed")
@pytest.mark.skipif(not SPEC_PATH.exists(), reason="contract YAML not found")
class TestM7AdminContract:
    """Static contract validation — no live server."""

    def setup_method(self):
        self.schema = schemathesis.openapi.from_path(str(SPEC_PATH))

    def test_spec_loads_without_error(self):
        ops = list(self.schema.get_all_operations())
        assert len(ops) > 0, "No operations found in m7-admin contract spec"

    def test_all_operations_have_responses(self):
        for result in self.schema.get_all_operations():
            op = result.ok()
            assert op.definition.raw.get("responses"), (
                f"Operation {op.method.upper()} {op.path} has no responses defined"
            )

    def test_request_generation(self):
        for result in self.schema.get_all_operations():
            op = result.ok()
            try:
                case = op.make_case()
                assert case is not None
            except Exception as exc:
                pytest.fail(
                    f"Failed to generate case for {op.method.upper()} {op.path}: {exc}"
                )
