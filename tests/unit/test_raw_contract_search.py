from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tsxapipy.api import schemas
from tsxapipy.api.client import APIClient
from tsxapipy.api.exceptions import APIResponseParsingError


def _client() -> APIClient:
    return APIClient(
        initial_token="unit-test-token",
        token_acquired_at=datetime.now(timezone.utc),
        api_base_url="https://unit.test",
    )


def _raw_contract_payload() -> dict:
    return {
        "contracts": [
            {
                "id": "CON.F.US.MNQ.M26",
                "name": "MNQM6",
                "description": "Micro E-mini Nasdaq-100: June 2026",
                "activeContract": True,
                "symbolId": "F.US.MNQ",
                "tickSize": 0.25,
                "tickValue": 0.5,
                "brokerOnlyField": {"preserved": True},
            }
        ],
        "success": True,
        "errorCode": 0,
        "errorMessage": None,
        "topLevelBrokerField": "preserved",
    }


def test_search_contracts_raw_preserves_active_contract():
    client = _client()
    raw_payload = _raw_contract_payload()
    client._post_request = Mock(return_value=raw_payload)

    raw = client.search_contracts_raw("MNQ", live=False)

    assert raw is raw_payload
    assert raw["contracts"][0]["activeContract"] is True


def test_search_contracts_raw_preserves_symbol_id_and_broker_only_fields():
    client = _client()
    raw_payload = _raw_contract_payload()
    client._post_request = Mock(return_value=raw_payload)

    raw = client.search_contracts_raw("MNQ")

    assert raw["contracts"][0]["symbolId"] == "F.US.MNQ"
    assert raw["contracts"][0]["brokerOnlyField"] == {"preserved": True}
    assert raw["topLevelBrokerField"] == "preserved"


def test_search_contracts_raw_calls_correct_endpoint_and_payload():
    client = _client()
    client._post_request = Mock(return_value=_raw_contract_payload())

    client.search_contracts_raw("MNQ", live=True)

    assert client._post_request.call_args.args[0] == "/api/Contract/search"
    assert client._post_request.call_args.args[1] == {"searchText": "MNQ", "live": True}


def test_search_contracts_raw_preserves_absent_contracts_key():
    client = _client()
    raw_payload = {"success": True, "errorCode": 0, "errorMessage": None}
    client._post_request = Mock(return_value=raw_payload)

    raw = client.search_contracts_raw("MNQ")

    assert raw is raw_payload
    assert "contracts" not in raw


def test_search_contracts_raw_malformed_non_object_fails_closed():
    client = _client()
    client._post_request = Mock(return_value=["not", "an", "object"])

    with pytest.raises(APIResponseParsingError, match="raw ContractSearchResponse"):
        client.search_contracts_raw("MNQ")


def test_search_contracts_unchanged_when_raw_contains_active_contract():
    client = _client()
    client._post_request = Mock(return_value=_raw_contract_payload())

    contracts = client.search_contracts("MNQ", live=False)

    assert len(contracts) == 1
    assert isinstance(contracts[0], schemas.Contract)
    assert contracts[0].id == "CON.F.US.MNQ.M26"
    assert contracts[0].tick_size == 0.25
    assert not hasattr(contracts[0], "activeContract")
    assert "activeContract" not in contracts[0].model_dump(by_alias=True)


def test_search_contract_by_id_unchanged():
    client = _client()
    client._post_request = Mock(return_value=_raw_contract_payload())

    contracts = client.search_contract_by_id("CON.F.US.MNQ.M26")

    assert len(contracts) == 1
    assert isinstance(contracts[0], schemas.Contract)
    assert contracts[0].id == "CON.F.US.MNQ.M26"
    assert client._post_request.call_args.args[0] == "/api/Contract/searchById"
    assert client._post_request.call_args.args[1] == {"contractId": "CON.F.US.MNQ.M26"}
