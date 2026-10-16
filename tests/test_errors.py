from google.genai.errors import ClientError
from rag_poc.errors import ProviderFailure, error_details
import pytest

@pytest.mark.parametrize("code,expected", [(400, "input"), (401, "credentials"), (403, "denied"), (404, "model"), (429, "limit")])
def test_provider_errors_are_useful_without_leaking_response(code, expected):
    raw = ClientError(code, {"error": {"message": "SECRET_TOKEN uploaded customer data", "status": "arbitrary"}})
    failure = ProviderFailure(raw)
    assert expected in str(failure).lower()
    assert f"HTTP {code}" in str(failure)
    assert "SECRET_TOKEN" not in str(failure)
    assert "uploaded customer data" not in str(error_details(failure))
