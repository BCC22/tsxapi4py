from datetime import datetime, timezone
from unittest.mock import Mock

from tsxapipy.api import schemas
from tsxapipy.api.client import APIClient
from tsxapipy.api.exceptions import (
    APIResponseError,
    APIResponseParsingError,
    APITimeoutError,
    InvalidParameterError,
)
from tsxapipy.trading.order_handler import OrderPlacer


ACCOUNT_ID = 1001
ORDER_ID = 9001
START = "2026-06-02T00:00:00Z"


def _client() -> APIClient:
    return APIClient(
        initial_token="unit-test-token",
        token_acquired_at=datetime.now(timezone.utc),
        api_base_url="https://unit.test",
    )


def _cancel_response(error_code=0):
    return schemas.CancelOrderResponse(success=True, errorCode=error_code, errorMessage=None)


def _order(status: int):
    return schemas.OrderDetails(id=ORDER_ID, status=status)


def _confirmed_client(open_orders=None, searched_orders=None, cancel_response=None) -> APIClient:
    client = _client()
    client.cancel_order = Mock(return_value=cancel_response or _cancel_response())
    client.search_open_orders = Mock(return_value=open_orders or [])
    client.search_orders = Mock(return_value=searched_orders or [])
    return client


def test_cancel_success_readback_absent_confirms():
    client = _confirmed_client(open_orders=[], searched_orders=[])

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.CONFIRMED
    assert result.readback_source == "searchOpen+search"


def test_cancel_success_search_open_still_live_fails():
    client = _confirmed_client(open_orders=[_order(status=1)])

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.FAILED
    assert result.readback_source == "searchOpen"
    assert result.readback_order_status == 1
    client.search_orders.assert_not_called()


def test_cancel_success_search_open_filled_race_lost_state():
    client = _confirmed_client(open_orders=[_order(status=2)])

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.RACE_LOST_FILLED
    assert result.readback_source == "searchOpen"
    assert result.readback_order_status == 2
    client.search_orders.assert_not_called()


def test_cancel_success_search_terminal_cancelled_confirms():
    client = _confirmed_client(open_orders=[], searched_orders=[_order(status=3)])

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.CONFIRMED
    assert result.readback_source == "search"
    assert result.readback_order_status == 3


def test_cancel_success_search_filled_race_lost_state():
    client = _confirmed_client(open_orders=[], searched_orders=[_order(status=2)])

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.RACE_LOST_FILLED
    assert result.readback_order_status == 2


def test_cancel_success_readback_timeout_unconfirmed():
    client = _confirmed_client(open_orders=[])
    client.search_open_orders.side_effect = APITimeoutError("read-back timed out")

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.UNCONFIRMED


def test_cancel_timeout_after_send_unconfirmed_not_failed():
    client = _client()
    client.cancel_order = Mock(side_effect=APITimeoutError("cancel timed out"))

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.UNCONFIRMED


def test_cancel_invalid_json_after_send_unconfirmed():
    client = _client()
    client.cancel_order = Mock(
        side_effect=APIResponseParsingError("invalid cancel response", raw_response_text="<html>")
    )

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.UNCONFIRMED


def test_cancel_success_nonzero_error_code_unconfirmed_without_readback():
    client = _confirmed_client(cancel_response=_cancel_response(error_code=7))
    client.search_open_orders.side_effect = APIResponseError("read-back failed", error_code=7)

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.UNCONFIRMED
    assert result.cancel_response.error_code == 7


def test_cancel_success_nonzero_error_code_can_confirm_only_with_readback_absence():
    client = _confirmed_client(
        open_orders=[],
        searched_orders=[],
        cancel_response=_cancel_response(error_code=7),
    )

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.CONFIRMED
    assert result.cancel_response.error_code == 7


def test_cancel_success_false_clean_rejection_failed():
    client = _client()
    client.cancel_order = Mock(side_effect=InvalidParameterError("bad cancel request"))

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.FAILED


def test_cancel_success_false_ambiguous_after_send_unconfirmed():
    client = _client()
    client.cancel_order = Mock(side_effect=APIResponseParsingError("ambiguous response"))

    result = client.cancel_order_with_confirmation(ACCOUNT_ID, ORDER_ID, START)

    assert result.state is schemas.CancelState.UNCONFIRMED


def test_search_open_orders_request_construction_and_empty_response():
    client = _client()
    client._post_request = Mock(return_value={"orders": [], "success": True, "errorCode": 0, "errorMessage": None})

    orders = client.search_open_orders(ACCOUNT_ID)

    assert orders == []
    assert client._post_request.call_args.args[0] == "/api/Order/searchOpen"
    assert client._post_request.call_args.args[1] == {"accountId": ACCOUNT_ID}


def test_search_open_orders_response_parsing_present():
    client = _client()
    client._post_request = Mock(
        return_value={
            "orders": [{"id": ORDER_ID, "status": 1}],
            "success": True,
            "errorCode": 0,
            "errorMessage": None,
        }
    )

    orders = client.search_open_orders(ACCOUNT_ID)

    assert len(orders) == 1
    assert orders[0].id == ORDER_ID
    assert orders[0].status == 1


def test_search_open_orders_response_parsing_error():
    client = _client()
    client._post_request = Mock(return_value={"orders": [{"id": "bad"}], "success": True})

    try:
        client.search_open_orders(ACCOUNT_ID)
    except APIResponseParsingError as exc:
        assert "SearchOpenOrdersResponse" in str(exc)
    else:
        raise AssertionError("expected parsing error")


def test_legacy_api_client_cancel_order_contract_preserved():
    client = _client()
    client._post_request = Mock(return_value={"success": True, "errorCode": 0, "errorMessage": None})

    response = client.cancel_order(ACCOUNT_ID, ORDER_ID)

    assert isinstance(response, schemas.CancelOrderResponse)
    assert response.success is True


def test_legacy_order_placer_cancel_order_contract_preserved():
    client = _client()
    client.cancel_order = Mock(return_value=_cancel_response())
    placer = OrderPlacer(client, account_id=ACCOUNT_ID)

    result = placer.cancel_order(ORDER_ID)

    assert result is True


def test_order_placer_cancel_order_with_confirmation_delegates_with_search_window():
    client = _client()
    expected = schemas.CancelResult(
        state=schemas.CancelState.CONFIRMED,
        account_id=ACCOUNT_ID,
        order_id=ORDER_ID,
        reason="confirmed",
    )
    client.cancel_order_with_confirmation = Mock(return_value=expected)
    placer = OrderPlacer(client, account_id=ACCOUNT_ID)

    result = placer.cancel_order_with_confirmation(ORDER_ID, search_window_minutes=15)

    assert result is expected
    kwargs = client.cancel_order_with_confirmation.call_args.kwargs
    assert kwargs["account_id"] == ACCOUNT_ID
    assert kwargs["order_id"] == ORDER_ID
    assert kwargs["search_start_timestamp_iso"].endswith("Z")
    assert kwargs["search_end_timestamp_iso"].endswith("Z")
