# TSXAPIPY SDK Debt Adjudication Inventory

**Arc:** SDK_DEBT_ADJUDICATION (opened after BD-1 read-certification closure at `f8f8f7e`)  
**BD-1 read runtime pin (certified, clean):** `95ce79fe61baba74a2f67faca0cfdb66571507af`  
**Inventory date:** 2026-06-01  
**Mode:** Read-only review — no SDK edits, no commit, no push, no broker HTTP, no auth, no order mutation, no realtime streams, no bots.

---

## 1. Provenance state

| Field | Value |
|--------|--------|
| **Clone path** | `C:\Users\bccie\tsxapi4py` |
| **Remote URL** | `https://github.com/mceesincus/tsxapi4py.git` (fetch + push) |
| **HEAD SHA** | `95ce79fe61baba74a2f67faca0cfdb66571507af` |
| **Branch** | `main` tracking `origin/main` |
| **HEAD reachable on origin** | **YES** — `git ls-remote origin 95ce79fe61baba74a2f67faca0cfdb66571507af` returned the object; branch tip matches pinned BD-1 install |
| **Working tree** | Dirty — 5 modified files only (no untracked SDK sources in `git status --short`) |

### Dirty file list

```
 M src/tsxapipy/api/client.py
 M src/tsxapipy/api/schemas.py
 M src/tsxapipy/real_time/data_stream.py
 M src/tsxapipy/real_time/user_hub_stream.py
 M src/tsxapipy/trading/order_handler.py
```

### Diff stat

```
 src/tsxapipy/api/client.py                |  44 ++-
 src/tsxapipy/api/schemas.py               |  12 +-
 src/tsxapipy/real_time/data_stream.py     |  20 +-
 src/tsxapipy/real_time/user_hub_stream.py | 596 ++++++++++++++++++++++++++++--
 src/tsxapipy/trading/order_handler.py     |  10 +-
 5 files changed, 627 insertions(+), 55 deletions(-)
```

**Interpretation:** Local clone is **byte-identical to upstream at HEAD** for all paths except these five files. BD-1 certified reads used the **clean** pin (`95ce79f` without this diff). Any process using `pip install -e` on this dirty clone is **not** on the certified read surface.

---

## 2. Change classification by file

**Risk anchor (failure consequence):**

| Rating | If this change is **wrong** |
|--------|-----------------------------|
| **CRITICAL** | Wrong order type/size/route; failed order looks successful; live position invisible |
| **HIGH** | Failed cancel hidden from operators; false order/position/account state confidence; realtime appears healthy when it is not |
| **MEDIUM** | Payload/schema diverges from broker → reject or mis-parse (no silent money move) |
| **LOW** | Logging/diagnostics only; no trading state impact |

---

### 2.1 `src/tsxapipy/api/schemas.py` (+12 / −12 lines)

| Item | Assessment |
|------|------------|
| **Functional summary** | `OrderBase.type` gains Pydantic alias `orderType`. All place-request models use `Field(..., alias="orderType")`. **Stop market** literal changes **`3` → `4`**. Trailing stop remains `5`. Comments assert TopstepX: 1=Limit, 2=Market, 4=Stop, 5=TrailingStop. |
| **Broker surfaces** | Order schemas; order placement payload shape |
| **Risk** | **CRITICAL** — wrong stop type does not fail locally; broker may accept a different order kind or reject unpredictably |
| **Relevance** | BD-1 read: **no** (reads do not place stops). Write-path: **yes**. Realtime: **no**. Paper/live: **yes** (via placement) |
| **Disposition** | **Required for correctness *if* spec is 4=Stop** — not optional polish. **Unsafe/unknown until spec-checked** |
| **Local vs upstream (same input)** | `OrderPlacer.place_stop_market(...)` → upstream emits **`type: 3`**; local emits **`type: 4`**. **Different wire behavior.** |
| **Spec cross-check (mm-futures, not live broker)** | `docs/rebuild/MERGED_TOPSTEPX_API_CONTRACT.md`: **Order/place** table cited as types **1,2,4,5,6,7**; **StopLimit=3** appears in **realtime enum**, not place table (U14/T_SB = empirical). Local **4=Stop** aligns with merged place table; upstream **3** likely conflates **StopLimit (3)** with **stop market (4)**. **Verdict: local change is plausibly correcting upstream; MUST be confirmed by official ProjectX Order/place docs + T_SB-style place test before acceptance.** |

---

### 2.2 `src/tsxapipy/trading/order_handler.py` (+10 / −10 lines)

| Item | Assessment |
|------|------------|
| **Functional summary** | `ORDER_TYPES_MAP["STOP"]`: **3 → 4**. Adds **`"TRAILING_STOP": 5`** to map (schema existed upstream; map entry was commented). Docstrings: stop market is API type **4**. |
| **Broker surfaces** | Order placement (via `OrderPlacer` → `APIClient.place_order`) |
| **Risk** | **CRITICAL** — same as schemas: `place_stop_market` path changes integer sent to API |
| **Relevance** | BD-1: **no**. Write-path: **yes**. Realtime/paper: **indirect** (placement only) |
| **Disposition** | **Required if stop=4 is spec**; **experimental/unsafe** until proven |
| **Local vs upstream** | Identical divergence: STOP string → **3 vs 4** |

---

### 2.3 `src/tsxapipy/api/client.py` (+44 lines net)

| Item | Assessment |
|------|------------|
| **Functional summary** | (1) `_post_request`: `suppress_debug_print` flag; extra debug log of POST URL + payload preview (truncated). (2) **Cancel** `errorCode == "5"`: log at **debug** not **error** (still raises mapped exception). (3) **`place_order`**: after `model_dump(by_alias=True)`, remap **`orderType` → `type`**, drop `orderType`, default type **2** if missing/non-int; **`logger.info`** on sent type. (4) **`search_open_positions`**: `suppress_debug_print=True`. |
| **Broker surfaces** | Request transport/logging; order placement payload; order cancellation logging; position search (read) |
| **Risk** | **place_order remap: CRITICAL** — wrong key or wrong default (`2` market) silently changes order type. **Cancel log demotion: HIGH** for ops visibility (exception path unchanged — does **not** hide failed cancel from code that catches `APIResponseError`). **Payload debug log: HIGH** credential/account leakage if DEBUG enabled in production. **suppress_debug_print: LOW** |
| **Relevance** | BD-1: **partial** — position search uses client; certified run did not depend on dirty client. Write-path: **yes** (place_order). Realtime: **no**. Paper: **yes** |
| **Disposition** | place_order block: **required pending spec**; cancel demotion: **optional** ops hygiene (mm-futures `SCRATCHPAD.md` documents intent); debug payload: **optional** but needs redaction policy |
| **Local vs upstream** | Upstream `place_order` sends `model_dump(by_alias=True)` only — with **local schemas**, dump may emit **`orderType`** not **`type`** unless remap runs; with **upstream schemas**, field is `type`. Local remap forces **`type`** integer — **intended fix** for wire contract; **default-to-2** on bad type is **unsafe** if ever triggered |

---

### 2.4 `src/tsxapipy/real_time/data_stream.py` (+20 / −20 lines)

| Item | Assessment |
|------|------------|
| **Functional summary** | Hub options: add **`max_size: None`**. Three `connection.send(...)` calls: pass **`invocation_id` as 4th argument**, `on_invocation=None` as 3rd (signalrcore API correction). Comments only on URL options otherwise. |
| **Broker surfaces** | Realtime market data; reconnect/subscribe invocation behavior |
| **Risk** | **HIGH** — wrong `send` arity → subscriptions never ack / no quotes while connection looks **CONNECTED** |
| **Relevance** | BD-1: **no** (99B noted import-side `DataStream` message only). Write-path: **no** directly. **Realtime certification: yes** |
| **Disposition** | **Required** for correct signalrcore usage if library signature is `(method, args, on_invocation, invocation_id)`; **unsafe** if applied to a different signalrcore version |
| **Local vs upstream** | Same subscribe intent; **different RPC invocation wiring** |

---

### 2.5 `src/tsxapipy/real_time/user_hub_stream.py` (+596 / −55 lines)

| Item | Assessment |
|------|------------|
| **Functional summary** | Large diagnostic and connectivity refactor: env-gated verbose mode (`TSXAPIPY_USERHUB_*`); **`token=` → `access_token=`** in hub URL; **`skip_negotiation: True`**, **`max_size: None`**; transport raw/decoded taps; **`GatewayLogout`** handler; **`invoke`-based** subscribe (`SubscribeOrders`, `SubscribePositions`, `SubscribeTrades`, `SubscribeAccounts`) replacing **`send("SubscribeTo*")`** names; transport-ready wait before subscribe; extensive **`print` + `_hub_diag` logging** on order/position/account/trade events; optional alt account duplicate subs; completion-message error handling in `_on_error_signalr`. |
| **Broker surfaces** | Realtime user/account/order/position/trade events; hub auth URL; subscribe RPCs; session conflict (`GatewayLogout`) |
| **Risk** | **HIGH** — false confidence (events print but callbacks fail); **HIGH** — wrong hub method names → no order/position events; **HIGH** — `access_token` vs `token` wrong → auth failure or silent disconnect; **MEDIUM** — `print` to stdout in library (ops noise, possible data exposure in event previews). Not CRITICAL for placement unless write-path trusts hub state without REST reconcile |
| **Relevance** | BD-1: **no**. Write-path: **indirect** (order state visibility). **Realtime certification: yes**. Paper/live: **yes** (state sync) |
| **Disposition** | Mix: **invoke + official method names + access_token** likely **required fixes** vs upstream; **diagnostic layer** is **experimental** (should not ship in production SDK without flags default-off) |
| **Local vs upstream** | Upstream uses `SubscribeToOrders` etc. via **`send`**; mm-futures merged contract §7 documents **`SubscribeOrders`**, **`SubscribePositions`**, **`SubscribeTrades`** — local aligns with merged doc, upstream may be stale/wrong |

---

## 3. Split recommendation (patch lanes + dependency order)

**Lane priority for downstream arcs:**

```text
WRITE-PATH GATE (resolve before write-path certification):
  P1 + order-relevant P2  →  blocks write-path

REALTIME GATE (separate arc; does not block write-path REST placement):
  P3 + P4  →  blocks realtime / paper state sync

LOWEST / RIDES ALONG:
  P5  →  attach to lane it touches; do not block alone
```

| Lane | Scope | Files / hunks | Gates |
|------|--------|---------------|--------|
| **SDK-P1** | Order schema + handler correctness | `schemas.py`, `order_handler.py` | **Write-path** |
| **SDK-P2** | API client place/cancel/logging | `client.py` `place_order`, cancel log demotion, `_post_request` debug | **Write-path** (place); cancel demotion is ops |
| **SDK-P3** | Market hub stream | `data_stream.py` | **Realtime** |
| **SDK-P4** | User hub stream | `user_hub_stream.py` (split: **P4a** connectivity/subscribe/auth, **P4b** diagnostics-only) | **Realtime** / paper sync |
| **SDK-P5** | Diagnostics-only | `suppress_debug_print`, verbose env taps, `print` probes, alt-account env | **Neither** alone |

**Suggested review order:** P1 → P2 (place path) → P4a → P3 → P4b → P5.

---

## 4. Institutional risk flags

| Flag | Present? | Where / note |
|------|----------|----------------|
| Could move money | **YES** | P1/P2: stop **3→4**, `orderType`/`type` remap, default type **2** |
| Could hide failed cancels | **PARTIAL** | P2: only log level; **exception still raised** — risk is human/log pipeline, not silent success |
| False order-state confidence | **YES** | P4: noisy prints without guaranteed callback delivery; parse-failure warnings added but not fail-closed |
| Credential / account data leak | **YES** | P2 DEBUG payload log; P4 verbose raw transport previews |
| Silent endpoint payload change | **YES** | P1/P2 change JSON `type` field semantics |
| Realtime appears healthier than reality | **YES** | P3/P4: connected + subscribe prints while wrong `send`/`invoke` or wrong token param |
| **Local vs upstream different order for same input** | **YES** | STOP market: **3 (upstream) vs 4 (local)**; place payload may send **`orderType` vs `type`** without P2 remap |

---

## 5. Required evidence before acceptance

### SDK-P1 (order schema / handler)

| Evidence | Required |
|----------|----------|
| Mocked unit tests | Assert `PlaceStopOrderRequest` serializes **`type: 4`**; `ORDER_TYPES_MAP["STOP"] == 4`; trailing stop **5** |
| Contract / API docs | Official ProjectX **Order/place** `type` enum vs realtime **OrderType** enum (resolve 3=StopLimit vs 4=Stop) |
| Broker HTTP | **Yes** — T_SB-style place: stop market + confirm reject/accept for type 3 vs 4 |
| Order mutation | **Yes** — controlled sim practice only, after authorization |
| Realtime | No |
| mm-futures dependency | Do not pin dirty SDK for write-path until P1 accepted or discarded with documented upstream behavior |

### SDK-P2 (client place / cancel / logging)

| Evidence | Required |
|----------|----------|
| Mocked unit tests | `place_order` dump → wire dict has **`type` int only**, no `orderType`; cancel code 5 uses `debug` and still raises |
| Contract docs | Confirm wire field name **`type`** (not `orderType`) on Order/place |
| Broker HTTP | Place market/limit/stop/trailing once each in sim |
| Order mutation | **Yes** |
| Realtime | No |
| mm-futures | `launch.py`-style check for `benign_cancel_noop` if cancel demotion kept |

### SDK-P3 (market data stream)

| Evidence | Required |
|----------|----------|
| Mocked unit tests | `send` called with `(method, [contract_id], None, invocation_id)` |
| Contract docs | signalrcore version + ProjectX market hub subscribe method names |
| Broker HTTP | No (initially) |
| Realtime stream | **Yes** — quote/trade subscription receives frames |
| mm-futures | Separate realtime cert arc |

### SDK-P4 (user hub)

| Evidence | Required |
|----------|----------|
| Mocked unit tests | URL contains `access_token=`; `invoke("SubscribeOrders", [account_id], ...)` |
| Contract docs | User hub URL auth param; subscribe RPC names per ProjectX realtime reference |
| Broker HTTP | No |
| Realtime stream | **Yes** — order/position events after subscribe |
| mm-futures | Strip or gate **P4b** diagnostics before production depend |

### SDK-P5 (diagnostics)

| Evidence | Required |
|----------|----------|
| Mocked unit tests | Env flags default off; no `print` when unset |
| Broker / realtime | No |
| mm-futures | Never required for write-path |

---

## 6. Decision options

| Option | Meaning |
|--------|---------|
| **DISCARD_ALL_LOCAL_DIFF_AND_USE_UPSTREAM** | Revert 5 files; mm-futures stays on clean `95ce79f`; accept upstream stop=3 until upstream fixes |
| **PUSH_ENTIRE_LOCAL_DIFF** | Single upstream PR/commit as-is (includes ~596 lines diagnostics) — **not recommended** without P4 split |
| **SPLIT_AND_REVIEW_PATCH_LANES** | P1→P2→P4a→P3→P4b→P5; evidence per lane; pin only accepted lanes |
| **VENDOR/FORK_TSXAPIPY_FOR_MM_FUTURES** | Maintain `mm-futures` fork with explicit lane tags and pins — if upstream inactive |
| **HOLD_WRITE_PATH_CERTIFICATION** | Default until P1+P2 adjudicated |

---

## 7. Recommendation

**SPLIT_AND_REVIEW_PATCH_LANES**

**Why:**

1. **627 lines are not one concern** — ~94% of line delta is `user_hub_stream.py` diagnostics; order semantics are a small, **CRITICAL** surface that must not be held hostage to hub logging.
2. **Write-path can proceed after P1+P2 only** — realtime lanes (P3/P4) gate a **different** arc (per BD-1 closure and import-closure discipline).
3. **Discard-all is unsafe until proven** — merged mm-futures contract material indicates **Order/place types 1,2,4,5,…** while upstream SDK maps STOP→**3**; blind discard may **reintroduce wrong stop placement**.
4. **Push-all is unsafe** — unreviewed `print`/transport taps and env opt-outs belong in P4b/P5, not production pin.
5. **P1 order-lane direction (spec-informed, not broker-tested here):** treat stop **4** and `type` wire remap as **candidate fixes**, not experiments — **mandatory broker evidence (T_SB + stop market place)** before pin.

---

## 8. Explicit boundary

This memo:

- Does **not** authorize SDK edits, commits, or pushes  
- Does **not** authorize broker HTTP, authentication, order mutation, or realtime streams  
- Does **not** authorize write-path certification, paper trading, or live trading  
- Does **not** certify local dirty SDK behavior (BD-1 used clean `95ce79f` only)

---

## TSXAPIPY_SDK_DEBT_ADJUDICATION_INVENTORY_BUNDLE

| Field | Value |
|--------|--------|
| **Files inspected** | `src/tsxapipy/api/client.py`, `schemas.py`, `real_time/data_stream.py`, `real_time/user_hub_stream.py`, `trading/order_handler.py`; provenance via git; mm-futures `MERGED_TOPSTEPX_API_CONTRACT.md`, `CHATGPT_BROKER_API_CONTRACT_RESEARCH.md`, `SCRATCHPAD.md` (spec context only) |
| **Files modified/created** | **Created:** `SDK_DEBT_ADJUDICATION_INVENTORY.md` (this memo). **SDK source:** unchanged (read-only) |
| **Remote** | `https://github.com/mceesincus/tsxapi4py.git` |
| **HEAD** | `95ce79fe61baba74a2f67faca0cfdb66571507af` (matches `origin/main`) |
| **Dirty diff stat** | 5 files, **627 insertions**, **55 deletions** |
| **Recommended patch lanes** | **P1** → **P2** → **P4a** → **P3** → **P4b** → **P5** (write-path: P1+P2 only) |
| **Highest-risk change** | **Stop order type 3 → 4** (`schemas.py` + `order_handler.py`) + **`place_order` `type`/`orderType` remap** — CRITICAL: same strategy input, different order type vs clean upstream |
| **Recommended decision** | **SPLIT_AND_REVIEW_PATCH_LANES** |
| **Broker HTTP** | **NO** |
| **Auth** | **NO** |
| **Order mutation** | **NO** |
| **Realtime** | **NO** |
| **Commit status** | **NO** commit (inventory only) |
| **READY_FOR_R&D_REVIEW** | **YES** |
| **READY_FOR_WRITE_PATH_CERTIFICATION** | **NO** |

---

*Inventory commands executed: `git remote -v`, `git rev-parse HEAD`, `git status --short`, `git diff --stat`, per-file `git diff` on all five paths; `git ls-remote` / `git branch -vv` for origin reachability.*
