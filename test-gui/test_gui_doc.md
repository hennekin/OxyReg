### 2.1 Architecture — three parts, one queue

| Part                        | Runs in               | Responsibility                                                |
| --------------------------- | --------------------- | ------------------------------------------------------------- |
| `App` (tkinter GUI)         | **main thread**       | Draws the board, shows the traffic log. Never opens a socket. |
| `BoardServer.serve_forever` | background thread     | Blocks in `accept()`, spawns one thread per client.           |
| `BoardServer._handle`       | one thread per client | Receives bytes, splits them into lines, validates, replies.   |

**Why the queue?** tkinter is _not thread-safe_ — a socket thread must never call tkinter directly. So the server threads only put messages into a `queue.Queue` (`inbox`), and the GUI polls that queue every 60 ms via `after()`. This is the standard, race-free pattern for "socket + GUI" in Python.

One request travels through the system like this:

```
your client            server thread (per client)        GUI (main thread)
    │                        │                                │
    │── {"cmd":"set",...}\n ─▶                                │
    │                        │ parse + validate (pure logic)  │
    │                        │── ("traffic", line, resp) ────▶│ log: ← request / → response
    │                        │── ("apply", ("set",4,"X")) ───▶│ animate X into cell 4
    │◀── {"status": "ok"}\n ─│                                │
```

A lock (`self.order`) guarantees that with several clients at once, _log order = board order = reply order_.

### 2.2 The key TCP lesson: framing

TCP is a **byte stream**, not a message protocol. If a client sends two requests quickly, they may arrive in one `recv()`; one request may arrive in three pieces. The program therefore defines its own message boundary:

> **One JSON object per line, UTF-8 encoded, terminated by `\n` (newline-delimited JSON).**

The receiver keeps a buffer and only processes it when it contains a full line:

```python
buf += chunk
while b"\n" in buf:
    line, buf = buf.split(b"\n", 1)   # take one complete message
    ...                               # rest stays in the buffer
```

The same rule applies in both directions: every response is also one JSON line terminated by `\n`.

### 2.3 Design rules (deliberate, per your spec)

- **The board is a pure display.** The _only_ way to change it is TCP. There is intentionally no reset button and no clickable cells — the socket is the single source of truth.
- **No game rules.** No turns, no win detection, no "cell occupied" check. Setting a mark on an occupied cell **overwrites** it. Last write wins.
- **Every request gets exactly one response line**, in the same order the requests arrived on that connection.

---

## 3. API reference

### 3.1 Endpoint & framing

|                 |                                                                    |
| --------------- | ------------------------------------------------------------------ |
| Transport       | TCP                                                                |
| Default address | `127.0.0.1:6543` (override port: `python tcp_tictactoe.py <port>`) |
| Encoding        | UTF-8                                                              |
| Request format  | one JSON **object** per line, terminated by `\n`                   |
| Response format | one JSON **object** per line, terminated by `\n`                   |
| Concurrency     | any number of clients, connections may stay open                   |

### 3.2 Cell numbering (row-major, top-left = 0)

```
 0 | 1 | 2
---+---+---
 3 | 4 | 5
---+---+---
 6 | 7 | 8
```

(The GUI shows these numbers small in each cell's corner.)

### 3.3 Commands

**`set`** — draw a mark in a cell.

| Field  | Type    | Required | Allowed values | Notes              |
| ------ | ------- | -------- | -------------- | ------------------ |
| `cmd`  | string  | yes      | `"set"`        |                    |
| `cell` | integer | yes      | `0`–`8`        | row-major, see 3.2 |
| `mark` | string  | yes      | `"X"` or `"O"` | case-sensitive     |

```json
{ "cmd": "set", "cell": 4, "mark": "X" }
```

**`reset`** — clear all nine cells.

| Field | Type   | Required | Allowed values |
| ----- | ------ | -------- | -------------- |
| `cmd` | string | yes      | `"reset"`      |

```json
{ "cmd": "reset" }
```

Unknown extra fields are **ignored** (you can send `{"cmd":"reset","foo":1}` — it still works).

### 3.4 Responses

Every request line produces exactly one response line.

Success:

```json
{ "status": "ok" }
```

Failure:

```json
{ "status": "error", "error": "<message>" }
```

### 3.5 Error catalog (exact messages)

Validation stops at the first failure, in the order `cmd` → `cell` → `mark`.

| `error` value                   | Trigger                                                              |
| ------------------------------- | -------------------------------------------------------------------- |
| `invalid json`                  | line is not valid UTF-8 or not parseable JSON                        |
| `empty request`                 | line is empty / whitespace only                                      |
| `request must be a JSON object` | JSON is an array, string, number, …                                  |
| `missing field: cmd`            | `cmd` absent (or `null`)                                             |
| `unknown command`               | `cmd` is neither `"set"` nor `"reset"`                               |
| `missing field: cell`           | `set` without `cell`                                                 |
| `missing field: mark`           | `set` without `mark`                                                 |
| `invalid cell`                  | `cell` is not an integer in `0`–`8` (e.g. `4.0`, `"4"`, `9`, `true`) |
| `invalid mark`                  | `mark` is not exactly `"X"` or `"O"` (e.g. `"x"`)                    |

### 3.6 What actually goes over the wire

Request bytes (exactly):

```
{"cmd":"set","cell":4,"mark":"X"}\n
```

Response bytes (exactly):

```
{"status": "ok"}\n
```

(`\n` = byte `0x0A`. The space after `:` in responses comes from Python's `json.dumps`; your client should simply `json.loads` the line, not compare strings.)

---

## 4. Calling the API — examples

### 4.1 One-shot with `nc` (Linux/macOS/WSL)

```bash
printf '{"cmd":"set","cell":4,"mark":"X"}\n' | nc 127.0.0.1 6543
printf '{"cmd":"reset"}\n'                   | nc 127.0.0.1 6543
```

### 4.2 Interactive session with `nc`

```bash
nc 127.0.0.1 6543
{"cmd":"set","cell":0,"mark":"O"}     ← you type this line + Enter
{"status": "ok"}                      ← server replies
{"cmd":"set","cell":8,"mark":"X"}
{"status": "ok"}
```

### 4.3 Watch the animations: staggered requests

```bash
for i in 0 2 4 6 8; do
  printf '{"cmd":"set","cell":%d,"mark":"X"}\n' "$i"
  sleep 0.3
done | nc 127.0.0.1 6543
```

### 4.4 Python client (cross-platform) — `client_example.py`

```python
#!/usr/bin/env python3
"""Tiny companion client for tcp_tictactoe.py."""
import json
import socket

HOST, PORT = "127.0.0.1", 6543
sock = socket.create_connection((HOST, PORT))

def call(request: dict) -> dict:
    """Send one JSON line, read one JSON line back."""
    sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
    buf = b""
    while b"\n" not in buf:               # wait for the complete line
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("server closed the connection")
        buf += chunk
    line, _ = buf.split(b"\n", 1)
    return json.loads(line)

print(call({"cmd": "set", "cell": 4, "mark": "X"}))   # {'status': 'ok'}
print(call({"cmd": "set", "cell": 0, "mark": "O"}))   # {'status': 'ok'}
print(call({"cmd": "set", "cell": 9, "mark": "X"}))   # {'status': 'error', 'error': 'invalid cell'}
print(call({"cmd": "reset"}))                         # {'status': 'ok'}

sock.close()
```

---

## 5. Behavior & edge cases

| Situation                          | Behavior                                                                                                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `set` on an occupied cell          | Overwritten, no error (this is a drawing board, not a referee)                                               |
| Five `X` in a row                  | Perfectly fine — no turn or win logic exists                                                                 |
| `reset` on an empty board          | Succeeds with `{"status": "ok"}`                                                                             |
| Several clients at once            | All accepted; commands are applied in arrival order; each client only receives replies to _its own_ requests |
| Client sends requests back-to-back | Fine — the server splits the stream on `\n` and answers line by line, in order                               |
| Client disconnects                 | Logged in the GUI ("client disconnected"); board state is untouched                                          |
| Request without trailing `\n`      | The server **waits** for the newline before answering (this is framing, not a bug)                           |

---

## 6. Troubleshooting

| Symptom                                          | Cause / fix                                                                                                                    |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `ConnectionRefusedError` in the client           | Server not running, or wrong port. Start `python tcp_tictactoe.py` first.                                                      |
| Request sent, but no response                    | Missing `\n` terminator — the server answers per _line_.                                                                       |
| `cannot bind 127.0.0.1:6543 ...`                 | Port already in use. Use another port: `python tcp_tictactoe.py 7000` (and match it in your client).                           |
| `invalid json`                                   | Shell quoting problem. Use `printf` with single quotes as in 4.1, or the Python client.                                        |
| `ModuleNotFoundError: No module named 'tkinter'` | On Debian/Ubuntu: `sudo apt install python3-tk`.                                                                               |
| Want to control from another machine             | Change `HOST` in the script to `"0.0.0.0"` — but note there is **no authentication whatsoever**; keep it on a trusted network. |

That's the whole system: two commands (`set`, `reset`), one response shape (`ok` / `error`), newline-delimited JSON over TCP on port 6543 — everything in the code, the examples, and this documentation uses exactly those conventions. Happy socket practicing!
