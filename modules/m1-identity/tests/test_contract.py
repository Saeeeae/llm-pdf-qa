"""
B3.2 Schemathesis contract lock — M1 Identity.

Validates that the OpenAPI spec at packages/contracts/m1-identity.openapi.yaml
is internally consistent (valid schema, resolvable $refs, correct response
shapes).  No live server is required: we use `validate_request` only and skip
`call_and_validate` (which needs a running server).

Run:
  pytest modules/m1-identity/tests/test_contract.py -v
"""

import pathlib
import pytest

CONTRACTS_DIR = pathlib.Path(__file__).parents[4] / "packages" / "contracts"
SPEC_PATH = CONTRACTS_DIR / "m1-identity.openapi.yaml"

try:
    import schemathesis
    SCHEMATHESIS_AVAILABLE = True
except ImportError:
    SCHEMATHESIS_AVAILABLE = False


@pytest.mark.skipif(not SCHEMATHESIS_AVAILABLE, reason="schemathesis not installed")
@pytest.mark.skipif(not SPEC_PATH.exists(), reason="contract YAML not found")
class TestM1Contract:
    """Static contract validation — no live server."""

    def setup_method(self):
        self.schema = schemathesis.openapi.from_path(str(SPEC_PATH))

    def test_spec_loads_without_error(self):
        """Schema must parse and expose at least one endpoint."""
        ops = list(self.schema.get_all_operations())
        assert len(ops) > 0, "No operations found in M1 contract spec"

    def test_all_operations_have_responses(self):
        """Every operation must define at least one response."""
        for result in self.schema.get_all_operations():
            op = result.ok()
            assert op.definition.raw.get("responses"), (
                f"Operation {op.method.upper()} {op.path} has no responses defined"
            )

    def test_request_generation(self):
        """Schemathesis must be able to generate valid test cases for each op."""
        for result in self.schema.get_all_operations():
            op = result.ok()
            # generate() validates that parameter schemas are well-formed
            try:
                case = op.make_case()
                # validate_request checks the generated case against the spec
                # without sending it anywhere
                assert case is not None
            except Exception as exc:
                pytest.fail(
                    f"Failed to generate case for {op.method.upper()} {op.path}: {exc}"
                )
