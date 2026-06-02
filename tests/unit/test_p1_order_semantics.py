from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tsxapipy.api.client import APIClient
from tsxapipy.api.exceptions import InvalidParameterError
from tsxapipy.api import schemas
from tsxapipy.trading.order_handler import ORDER_TYPES_MAP, OrderPlacer


def _client_with_spy_response():
    client = APIClient(
        initial_token="unit-test-token",
        token_acquired_at=datetime.now(timezone.utc),
        api_base_url="https://unit.test",
    )
    client._post_request = Mock(
        return_value={
            "orderId": 123,
            "success": True,
            "errorCode": 0,
            "errorMessage": None,
        }
    )
    return client


def _sent_payload(client):
    assert client._post_request.call_count == 1
    return client._post_request.call_args.args[1]


@pytest.mark.parametrize(
    ("model", "expected_type", "expected_price_key"),
    [
        (
            schemas.PlaceMarketOrderRequest(
                accountId=1,
                contractId="CON.F.US.MNQ.M26",
                type=2,
                side=0,
                size=1,
            ),
            2,
            None,
        ),
        (
            schemas.PlaceLimitOrderRequest(
                accountId=1,
                contractId="CON.F.US.MNQ.M26",
                type=1,
                side=0,
                size=1,
                limitPrice=100.25,
            ),
            1,
            "limitPrice",
        ),
        (
            schemas.PlaceStopOrderRequest(
                accountId=1,
                contractId="CON.F.US.MNQ.M26",
                type=4,
                side=1,
                size=1,
                stopPrice=99.75,
            ),
            4,
            "stopPrice",
        ),
        (
            schemas.PlaceTrailingStopOrderRequest(
                accountId=1,
                contractId="CON.F.US.MNQ.M26",
                type=5,
                side=1,
                size=1,
                trailPrice=4.0,
            ),
            5,
            "trailPrice",
        ),
    ],
)
def test_place_order_emits_projectx_type_key_only(model, expected_type, expected_price_key):
    client = _client_with_spy_response()

    client.place_order(model)

    payload = _sent_payload(client)
    assert payload["type"] == expected_type
    assert "orderType" not in payload
    if expected_price_key:
        assert expected_price_key in payload


def test_stop_market_order_handler_builds_type_4_request():
    client = _client_with_spy_response()
    placer = OrderPlacer(client, account_id=1, default_contract_id="CON.F.US.MNQ.M26")

    order_id = placer.place_stop_market_order(side="SELL", size=1, stop_price=99.75)

    assert order_id == 123
    payload = _sent_payload(client)
    assert ORDER_TYPES_MAP["STOP"] == 4
    assert payload["type"] == 4
    assert payload["stopPrice"] == 99.75
    assert "orderType" not in payload


def test_trailing_stop_order_handler_preserves_trail_price_and_type_5():
    client = _client_with_spy_response()
    placer = OrderPlacer(client, account_id=1, default_contract_id="CON.F.US.MNQ.M26")

    model = placer._create_order_request_model(
        contract_id="CON.F.US.MNQ.M26",
        order_type_str="TRAILING_STOP",
        side_str="SELL",
        size=1,
        trail_price=4.0,
    )
    client.place_order(model)

    payload = _sent_payload(client)
    assert payload["type"] == 5
    assert payload["trailPrice"] == 4.0
    assert "orderType" not in payload


def test_unknown_order_type_fails_before_dispatch():
    client = _client_with_spy_response()
    placer = OrderPlacer(client, account_id=1, default_contract_id="CON.F.US.MNQ.M26")
    client._post_request.side_effect = AssertionError("dispatch must not occur")

    with pytest.raises(ValueError):
        placer.place_order(
            contract_id="CON.F.US.MNQ.M26",
            order_type="STOP_LIMIT",
            side="SELL",
            size=1,
            stop_price=99.75,
        )

    client._post_request.assert_not_called()


def test_missing_stop_price_fails_before_dispatch():
    client = _client_with_spy_response()
    placer = OrderPlacer(client, account_id=1, default_contract_id="CON.F.US.MNQ.M26")
    client._post_request.side_effect = AssertionError("dispatch must not occur")

    with pytest.raises(ValueError):
        placer.place_order(
            contract_id="CON.F.US.MNQ.M26",
            order_type="STOP",
            side="SELL",
            size=1,
        )

    client._post_request.assert_not_called()


def test_missing_trail_price_fails_before_dispatch():
    client = _client_with_spy_response()
    placer = OrderPlacer(client, account_id=1, default_contract_id="CON.F.US.MNQ.M26")
    client._post_request.side_effect = AssertionError("dispatch must not occur")

    with pytest.raises(ValueError):
        placer.place_order(
            contract_id="CON.F.US.MNQ.M26",
            order_type="TRAILING_STOP",
            side="SELL",
            size=1,
        )

    client._post_request.assert_not_called()


def test_unsupported_type_3_fails_closed_without_dispatch():
    client = _client_with_spy_response()
    client._post_request.side_effect = AssertionError("dispatch must not occur")
    model = schemas.OrderBase(
        accountId=1,
        contractId="CON.F.US.MNQ.M26",
        type=3,
        side=1,
        size=1,
    )

    with pytest.raises(InvalidParameterError):
        client.place_order(model)

    client._post_request.assert_not_called()


class _MalformedDumpOrder(schemas.OrderBase):
    def model_dump(self, *args, **kwargs):
        return {
            "accountId": 1,
            "contractId": "CON.F.US.MNQ.M26",
            "orderType": "STOP",
            "side": 1,
            "size": 1,
            "stopPrice": 99.75,
        }


def test_malformed_order_type_does_not_fallback_to_market():
    client = _client_with_spy_response()
    client._post_request.side_effect = AssertionError("dispatch must not occur")
    model = _MalformedDumpOrder(
        accountId=1,
        contractId="CON.F.US.MNQ.M26",
        type=4,
        side=1,
        size=1,
    )

    with pytest.raises(InvalidParameterError):
        client.place_order(model)

    client._post_request.assert_not_called()
