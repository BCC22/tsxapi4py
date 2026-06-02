# SDK-P1 Order Semantics Specification

**Arc:** SDK debt adjudication, P1 order semantics  
**Status:** Documentation/review only  
**Date:** 2026-06-01  
**SDK HEAD:** `95ce79fe61baba74a2f67faca0cfdb66571507af`  

This memo is spec-locked to the official ProjectX order-placement docs and the local dirty `tsxapi4py` diff. It does not certify broker execution.

---

## 1. Scope

P1 includes only the SDK surface needed to construct order-placement payloads correctly:

- `src/tsxapipy/api/schemas.py`
- `src/tsxapipy/trading/order_handler.py`
- the minimal `src/tsxapipy/api/client.py` `place_order` payload normalization seam, if required to guarantee the wire payload uses official ProjectX field names.

P1 explicitly excludes:

- `Order/cancel` behavior, cancel error taxonomy, and cancel logging
- request logging/debug payload logging outside the minimum `place_order` seam
- `search_open_positions` debug suppression
- `DataStream`
- `UserHubStream`
- realtime subscription/session behavior
- diagnostics-only stdout/logging probes
- broker mutation tests

---

## 2. Official Spec Evidence

### Primary source: ProjectX `Order/place`

Source: [Place an Order | ProjectX API Documentation](https://gateway.docs.projectx.com/docs/api-reference/order/order-place)

Official endpoint:

```text
POST https://api.topstepx.com/api/Order/place
```

Official required request fields include:

```text
accountId
contractId
type
side
size
```

The official request field is `type`, not `orderType`.

Official `Order/place` type enum:

```text
1 = Limit
2 = Market
4 = Stop
5 = TrailingStop
6 = JoinBid
7 = JoinAsk
```

The official `Order/place` parameter table does **not** list `3` as a valid placement value.

The same page documents bracket `type` fields using the same enum values:

```text
1 = Limit
2 = Market
4 = Stop
5 = TrailingStop
6 = JoinBid
7 = JoinAsk
```

Its example request uses `type` for both the primary order and bracket objects:

```json
{
  "accountId": 465,
  "contractId": "CON.F.US.DA6.M25",
  "type": 2,
  "side": 1,
  "size": 1,
  "limitPrice": null,
  "stopPrice": null,
  "trailPrice": null,
  "customTag": null,
  "stopLossBracket": {
    "ticks": 10,
    "type": 4
  },
  "takeProfitBracket": {
    "ticks": 20,
    "type": 1
  }
}
```

### Supporting source: Placing Your First Order

Source: [Placing Your First Order | ProjectX API Documentation](https://gateway.docs.projectx.com/docs/getting-started/placing-your-first-order)

The official getting-started example also uses `type`, not `orderType`:

```json
{
  "accountId": 1,
  "contractId": "CON.F.US.BP6.U25",
  "type": 2,
  "side": 1,
  "size": 1
}
```

### Supporting source: Search Open Orders

Source: [Search for Open Orders | ProjectX API Documentation](https://gateway.docs.projectx.com/docs/api-reference/order/order-search-open/)

The official open-order response example includes a stop-like open order with:

```json
{
  "type": 4,
  "stopPrice": 5138.000000000
}
```

This is response evidence, not placement proof, but it is consistent with `4 = Stop`.

### Enum namespace finding

The mm-futures research record preserves a separate enum concern: ProjectX realtime/order-type material has cited:

```text
Unknown = 0
Limit = 1
Market = 2
StopLimit = 3
Stop = 4
TrailingStop = 5
JoinBid = 6
JoinAsk = 7
```

That does **not** make `3` valid for `Order/place`. Current official `Order/place` docs omit `3`. Therefore the upstream SDK's stop-market `3` is best classified as **enum namespace conflation**: it appears to use a value associated with StopLimit/realtime enum context for a stop-market placement path.

P1 scope ruling:

```text
Stop-market: IN P1, must use type=4.
TrailingStop: IN P1 only to preserve existing schema support for type=5.
StopLimit/type=3: OUT OF P1 and OUT OF write-path dependency until T_SB proves whether Order/place accepts it.
```

---

## 3. Local Diff Analysis

### Clean upstream behavior

At clean upstream `95ce79f`:

- `PlaceStopOrderRequest.type` is `Literal[3] = 3`.
- `ORDER_TYPES_MAP["STOP"]` is `3`.
- `OrderPlacer.place_stop_market_order(...)` calls `place_order(..., order_type="STOP", stop_price=...)`.
- `APIClient.place_order(...)` sends `order_payload_model.model_dump(by_alias=True, exclude_none=True)` without a P1-specific field-name normalization step.

Consequence:

```text
OrderPlacer.place_stop_market_order(...)
  -> PlaceStopOrderRequest(type=3, stopPrice=...)
  -> /api/Order/place payload can carry type=3 for a stop-market intent
```

That does not match the current official `Order/place` enum.

### Dirty local behavior

In the local dirty diff:

- `PlaceStopOrderRequest.type` changes to `Literal[4]`.
- `ORDER_TYPES_MAP["STOP"]` changes to `4`.
- comments/docstrings state `4 = Stop`.
- `PlaceTrailingStopOrderRequest.type` remains `Literal[5]`.
- `APIClient.place_order(...)` normalizes a dumped `orderType` key into wire key `type`.

Consequence:

```text
OrderPlacer.place_stop_market_order(...)
  -> PlaceStopOrderRequest(type=4, stopPrice=...)
  -> APIClient.place_order normalizes payload to type=4
```

This matches the official `Order/place` field name and stop enum value.

### Payload key behavior: `type` vs `orderType`

Official docs require `type`.

Current dirty `schemas.py` sets aliases like:

```text
type: Literal[4] = Field(4, alias="orderType")
```

The dirty `client.py` then remaps:

```text
orderType -> type
```

This can be accepted as a narrow P1 seam only if it is hardened. The current dirty implementation defaults a non-int/missing order type to market (`2`), which is not acceptable for P1.

P1 patch shape should require:

```text
place_order must emit "type" as an integer.
place_order must not emit "orderType".
place_order must fail closed if the model cannot produce a valid supported order type.
place_order must not silently default missing/non-int order type to Market.
```

### Caller intent and StopLimit scope

Caller search covered the SDK clone and mm-futures.

SDK local callers:

- `OrderPlacer.place_stop_market_order(...)` is the only SDK stop-market convenience path.
- SDK examples and bot scripts primarily use market/limit order placement in searched paths.
- No SDK caller found that intentionally requests StopLimit through `type=3`.

mm-futures callers:

- `execution/order_executor.py` declares:

```text
OrderType.STOP = 4
OrderType.TRAILING_STOP = 5
```

- `OrderExecutor._ensure_bracket_or_flatten(...)` places protective stop-loss orders through `order_placer.place_stop_market_order(...)`.
- `launch.py` re-bracket logic also calls `place_stop_market_order(...)`.
- `scripts/execution_certification.py` intended payload for the stop gate is `type=4`.
- `execution/order_executor.py` has a direct `PlaceTrailingStopOrderRequest(..., type=5, ...)` path for trailing stops.
- mm-futures docs treat StopLimit/type `3` as `T_SB` / empirical / out of scope until proven.

Conclusion:

```text
Current mm-futures stop callers intend stop-MARKET behavior, not StopLimit.
Switching stop-market construction from 3 to 4 aligns with caller intent.
No current searched caller depends on old type=3 semantics for placement.
StopLimit remains out of scope; P1 must not add or imply StopLimit support.
```

---

## 4. Required SDK P1 Patch Shape

### Include exactly these files

```text
src/tsxapipy/api/schemas.py
src/tsxapipy/trading/order_handler.py
src/tsxapipy/api/client.py
```

### Include exactly these semantic changes

`src/tsxapipy/api/schemas.py`:

- Correct stop-market placement model to `type = 4`.
- Preserve market `2`, limit `1`, trailing stop `5`.
- Ensure serialized placement payload can be normalized to official field `type`.
- Update stale comments that still state `3 = STOP`.
- Do **not** add StopLimit placement support in P1.

`src/tsxapipy/trading/order_handler.py`:

- Set `ORDER_TYPES_MAP["STOP"] = 4`.
- Preserve `LIMIT = 1`, `MARKET = 2`.
- Preserve/add `TRAILING_STOP = 5` only if the implementation can construct the supported schema safely.
- Ensure unsupported order type strings raise before any API call.
- Do **not** map StopLimit or raw `3` in P1.

`src/tsxapipy/api/client.py`:

- Include only the minimal `place_order` payload normalization required to guarantee official wire shape.
- Emit `type` as an integer.
- Remove/drop `orderType` from the outbound payload.
- Fail closed for missing, unsupported, or non-integer order type.
- Do **not** silently default to market (`2`).

### Exclude from P1

Exclude these dirty-client hunks from P1:

- `_post_request(..., suppress_debug_print=...)`
- debug logging of POST payloads
- cancel `errorCode == 5` log demotion
- `search_open_positions(..., suppress_debug_print=True)`

Exclude all realtime and diagnostics:

- `src/tsxapipy/real_time/data_stream.py`
- `src/tsxapipy/real_time/user_hub_stream.py`
- stdout prints, raw transport taps, env-gated hub diagnostics, alternate account probes

### Client split ruling

`client.py` should be split. P1 may include only `place_order` payload normalization. Cancel/logging/debug behavior belongs to P2/P5 and must not ride with P1.

---

## 5. Tests Required Before SDK P1 Acceptance

### Unit tests required

Market:

- `PlaceMarketOrderRequest` / `OrderPlacer.place_market_order` produces outbound payload with `type: 2`.
- Payload uses `type`, not `orderType`.

Limit:

- `PlaceLimitOrderRequest` / `OrderPlacer.place_limit_order` produces `type: 1` and `limitPrice`.
- Missing/invalid `limit_price` fails before HTTP.

Stop:

- `PlaceStopOrderRequest` / `OrderPlacer.place_stop_market_order` produces `type: 4` and `stopPrice`.
- Stop must never produce `type: 3`.

Trailing stop:

- If retained as supported, `PlaceTrailingStopOrderRequest` produces `type: 5` and `trailPrice`.
- If not fully supported through `OrderPlacer`, tests must document schema-only support vs convenience-method support.

Unknown/unsupported:

- unsupported order type strings fail closed.
- raw or unknown `type` values do not silently default to `2`.
- StopLimit/type `3` is not accepted through P1 unless explicitly added under a separate StopLimit spec.

No broker contact:

- tests must mock `APIClient._post_request`.
- tests must assert no real `requests.Session.post` is called.
- no environment credentials are read for these unit tests.

Optional contract fixture:

- include a static fixture mirroring official ProjectX examples:
  - request key `type`
  - stop bracket `type: 4`
  - market order `type: 2`

---

## 6. Broker Evidence Required Later

P1 can be accepted as **code/spec aligned** before live broker mutation if:

- official docs are cited and locked,
- unit tests prove the SDK constructs official payloads,
- unsupported/unknown types fail closed,
- P1 is not bundled with P2/P3/P4/P5.

P1 cannot certify broker behavior. Before write-path certification can depend on this SDK surface, a separate authorized broker-mutation arc must prove the broker accepts and behaves correctly for the constructed payload.

Recommended later broker evidence:

```text
smallest possible practice/sim stop-market order placement
using official field type=4
with immediate cancellation or a non-fill-safe design
against confirmed practice/sim account only
under separate standalone authorization
with REST evidence capture and reconciliation
```

StopLimit/type `3` remains a separate empirical test (`T_SB`) and is not required for P1 stop-market correctness unless mm-futures decides to depend on StopLimit.

This memo does not authorize any broker HTTP, authentication, order placement, cancellation, modification, realtime streams, paper trading, or live trading.

---

## 7. Risk Assessment

### Consequence of leaving upstream `3`

Leaving clean upstream behavior in place can send `type: 3` for a stop-market intent. Current official `Order/place` docs do not list `3`. Failure modes:

- broker rejects the protective stop order;
- SDK/user believes stop-market placement was attempted correctly when payload was invalid;
- if broker interprets `3` as StopLimit or a different enum namespace, strategy intent can be silently changed.

This is a money-moving risk because protective stops are used to control open-position downside.

### Consequence of accepting local `4` without broker evidence

Accepting `4` is spec-aligned for construction, but still not broker-certified. Failure modes:

- docs are incomplete/stale relative to broker behavior;
- request may be accepted but exhibit unexpected order lifecycle behavior;
- stop placement may need additional price/tick constraints not captured in P1.

This is why broker mutation evidence is deferred to write-path certification.

### Consequence of mixing P1 with other lanes

Bundling P1 with realtime, cancel logging, or diagnostics would make a narrow order-semantics fix harder to review and risk shipping unrelated behavior:

- cancel log demotion could change operator visibility;
- debug payload logging could expose account/order data;
- UserHub/DataStream changes could create false order-state confidence;
- diagnostics could leak raw event payloads or obscure production logs.

P1 must stay narrow.

---

## 8. Decision Options

| Option | Meaning |
|--------|---------|
| **ACCEPT_P1_PATCH_SHAPE** | Lock the narrow patch shape above; proceed to unit/spec test design before any broker evidence. |
| **REVISE_P1_PATCH_SHAPE** | Change exact code boundaries, especially schema alias vs client normalization, before patching. |
| **DISCARD_LOCAL_P1_DIFF** | Reject stop `4` / `type` normalization and remain on upstream behavior. Not recommended against current docs. |
| **HOLD_WRITE_PATH_CERTIFICATION** | Required until P1 construction tests and later broker mutation evidence exist. |

---

## 9. Recommendation

**ACCEPT_P1_PATCH_SHAPE conditionally.**

Conditions before SDK P1 acceptance:

1. Split P1 from P2/P3/P4/P5.
2. Fix stop-market construction to `type: 4`.
3. Ensure outbound placement payloads use `type`, not `orderType`.
4. Fail closed on missing, unsupported, or non-integer order types; do not default to market.
5. Add unit tests for market, limit, stop, trailing stop if retained, unsupported types, and no broker HTTP.
6. State explicitly that StopLimit/type `3` is out of P1 and remains `T_SB` / empirical until separately certified.

Directional conclusion:

```text
Clean upstream type=3 for stop-market is likely wrong for ProjectX Order/place.
Dirty local type=4 is likely a correctness fix for stop-market.
The current dirty client default-to-market fallback must be revised before acceptance.
```

---

## 10. Boundary

This memo authorizes nothing beyond review.

```text
SDK_SOURCE_EDIT: NOT AUTHORIZED
SDK_COMMIT: NOT AUTHORIZED
SDK_PUSH: NOT AUTHORIZED
BROKER_HTTP: NOT AUTHORIZED
AUTHENTICATION: NOT AUTHORIZED
ORDER_PLACE_MODIFY_CANCEL: NOT AUTHORIZED
REALTIME_STREAMS: NOT AUTHORIZED
WRITE_PATH_CERTIFICATION: NOT AUTHORIZED
PAPER_LIVE_TRADING: NOT AUTHORIZED
```

---

## SDK_P1_ORDER_SEMANTICS_SPEC_BUNDLE

| Field | Value |
|--------|--------|
| **Files inspected** | `SDK_DEBT_ADJUDICATION_INVENTORY.md`; `src/tsxapipy/api/schemas.py`; `src/tsxapipy/trading/order_handler.py`; `src/tsxapipy/api/client.py`; caller references in `mm-futures/execution/order_executor.py`, `mm-futures/launch.py`, `mm-futures/scripts/execution_certification.py`, `mm-futures/docs/ORDER_EXECUTOR_AUDIT.md`; mm-futures spec docs for StopLimit/T_SB context |
| **Files created/modified** | Created `SDK_P1_ORDER_SEMANTICS_SPEC.md`; SDK source unchanged |
| **Official docs checked** | `https://gateway.docs.projectx.com/docs/api-reference/order/order-place`; `https://gateway.docs.projectx.com/docs/getting-started/placing-your-first-order`; `https://gateway.docs.projectx.com/docs/api-reference/order/order-search-open/` |
| **Clean vs dirty conclusion** | Clean upstream sends stop-market as `type: 3`; dirty local sends `type: 4` and normalizes toward wire key `type`; dirty direction matches official docs for stop-market, but client fallback must fail closed |
| **Recommended P1 patch shape** | `schemas.py` stop `4`; `order_handler.py` STOP `4`; minimal `client.py place_order` normalization to emit `type` only and reject unsupported/missing/non-int types |
| **Excluded lanes** | P2 cancel/logging/client debug; P3 `DataStream`; P4 `UserHubStream`; P5 diagnostics |
| **Broker HTTP** | NO |
| **Auth** | NO |
| **Order mutation** | NO |
| **Realtime** | NO |
| **Commit status** | NO commit |
| **READY_FOR_R&D_REVIEW** | YES |
| **READY_FOR_SDK_PATCHING** | NO |
| **READY_FOR_WRITE_PATH_CERTIFICATION** | NO |

