#!/usr/bin/env python3
"""
TCP Tic-Tac-Toe — a socket-practice board.

The GUI is a pure display: every mark on the board arrives as one JSON line
over TCP. No game rules, no turns, no winner — just draw and reset.

Run:    python test_gui.py [port]
Talk:   printf '{"cmd":"set","cell":4,"mark":"X"}\n' | nc 127.0.0.1 6543
"""

import json
import queue
import socket
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont

HOST = "127.0.0.1"          # change to "0.0.0.0" to allow other machines (no auth!)
DEFAULT_PORT = 6543

# ── palette ──────────────────────────────────────────────────────────────
INK       = "#0d1c20"   # window background
PANEL     = "#132b31"   # panels
BOARD_BG  = "#0a1f24"   # board canvas
GRID      = "#2d5a62"   # grid lines
TEXT      = "#e9f4f2"
DIM       = "#6f9596"
X_COLOR   = "#ff7a59"
O_COLOR   = "#45d6c3"
OK_COLOR  = "#8be28f"
ERR_COLOR = "#ff6b6b"
HOVER_BG  = "#14343b"


# ── protocol ─────────────────────────────────────────────────────────────

def ok():
    return {"status": "ok"}

def err(message):
    return {"status": "error", "error": message}

def parse_request(raw: bytes):
    """Validate one request line (without the trailing newline).

    Returns (event, response):
      event    – ("set", cell, mark) | ("reset",) | None
      response – the JSON-serializable reply dict
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, err("invalid json")
    if not text.strip():
        return None, err("empty request")
    try:
        req = json.loads(text)
    except json.JSONDecodeError:
        return None, err("invalid json")
    if not isinstance(req, dict):
        return None, err("request must be a JSON object")

    if "cmd" not in req or req["cmd"] is None:
        return None, err("missing field: cmd")
    cmd = req["cmd"]

    if cmd == "reset":
        return ("reset",), ok()

    if cmd == "set":
        if "cell" not in req:
            return None, err("missing field: cell")
        if "mark" not in req:
            return None, err("missing field: mark")
        cell, mark = req["cell"], req["mark"]
        if not (isinstance(cell, int) and not isinstance(cell, bool)
                and 0 <= cell <= 8):
            return None, err("invalid cell")
        if mark not in ("X", "O"):
            return None, err("invalid mark")
        return ("set", cell, mark), ok()

    return None, err("unknown command")


# ── TCP server (never touches tkinter!) ──────────────────────────────────

class BoardServer:
    """Accepts TCP connections, one thread per client.

    Talks to the GUI only through the `inbox` queue, because tkinter
    must only be used from the main thread.
    """

    def __init__(self, host, port, inbox):
        self.inbox = inbox
        self.order = threading.Lock()   # log order == board order == reply order
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(5)

    def serve_forever(self):
        while True:
            conn, addr = self.sock.accept()
            threading.Thread(target=self._handle, args=(conn, addr),
                             daemon=True).start()

    def _handle(self, conn, addr):
        peer = f"{addr[0]}:{addr[1]}"
        self.inbox.put(("connect", peer))
        buf = b""
        try:
            with conn:
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:               # client closed the connection
                        break
                    buf += chunk
                    # TCP is a byte stream: WE define the message boundary.
                    # Here: one JSON object per line, terminated by "\n".
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        with self.order:
                            event, resp = parse_request(line)
                            self.inbox.put(("traffic", line, resp))
                            if event is not None:
                                self.inbox.put(("apply", event))
                            conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
        except OSError:
            pass                                # client vanished mid-request
        finally:
            self.inbox.put(("disconnect", peer))


# ── GUI (main thread only) ───────────────────────────────────────────────

class App(tk.Tk):
    M = 16        # board margin
    C = 132       # cell size
    PAD = 34      # mark padding inside a cell
    STROKE = 9

    def __init__(self, host, port, inbox):
        super().__init__()
        self.inbox = inbox
        self.cells = [None] * 9                  # display copy: None | "X" | "O"
        self.mark_ids = [None] * 9               # canvas items per cell
        self.anim_token = [object() for _ in range(9)]
        self.last_ring = None
        self.clients = 0
        self._tick = 0
        self._error_shown = False

        self.title("TCP Tic-Tac-Toe")
        self.configure(bg=INK)
        self._fonts()
        self._build_ui(host, port)
        self.after(60, self._poll_inbox)         # bridge: queue -> GUI
        self.after(700, self._pulse)
        self._center()

    # ── setup ──

    def _fonts(self):
        fams = set(tkfont.families())
        disp = next((f for f in ("Trebuchet MS", "Verdana", "DejaVu Sans")
                     if f in fams), "TkDefaultFont")
        mono = tkfont.nametofont("TkFixedFont").cget("family")
        self.f_disp    = tkfont.Font(family=disp, size=20, weight="bold")
        self.f_sub     = tkfont.Font(family=disp, size=9)
        self.f_mono    = tkfont.Font(family=mono, size=10)
        self.f_mono_s  = tkfont.Font(family=mono, size=9)
        self.f_cellnum = tkfont.Font(family=mono, size=8)

    def _build_ui(self, host, port):
        W = 2 * self.M + 3 * self.C

        # header
        head = tk.Frame(self, bg=INK)
        head.pack(fill="x", padx=22, pady=(18, 12))
        top = tk.Frame(head, bg=INK)
        top.pack(fill="x")
        tk.Label(top, text="TCP", font=self.f_disp, fg=O_COLOR, bg=INK).pack(side="left")
        tk.Label(top, text=" TIC·TAC·TOE", font=self.f_disp, fg=TEXT, bg=INK).pack(side="left")
        chip = tk.Frame(top, bg=PANEL, padx=10, pady=5)
        chip.pack(side="right")
        self.dot = tk.Label(chip, text="●", font=self.f_mono, fg=O_COLOR, bg=PANEL)
        self.dot.pack(side="left")
        tk.Label(chip, text=f"LISTENING {host}:{port}",
                 font=self.f_mono_s, fg=TEXT, bg=PANEL).pack(side="left", padx=(5, 0))
        self.clients_lbl = tk.Label(head, text="clients connected: 0",
                                    font=self.f_mono_s, fg=DIM, bg=INK)
        self.clients_lbl.pack(anchor="e", pady=(6, 0))
        tk.Label(head, text="socket practice board — every mark arrives as a JSON line over TCP",
                 font=self.f_sub, fg=DIM, bg=INK, anchor="w").pack(anchor="w", pady=(6, 0))

        # board
        self.board = tk.Canvas(self, width=W, height=W, bg=BOARD_BG, highlightthickness=0)
        self.board.pack(padx=22)
        self.hover_id = self.board.create_rectangle(-10, -10, -10, -10,
                                                    fill=HOVER_BG, outline="")
        self._draw_grid()
        self.board.bind("<Motion>", self._on_motion)
        self.board.bind("<Leave>", self._on_leave)

        # traffic log
        log_frame = tk.Frame(self, bg=INK)
        log_frame.pack(fill="both", padx=22, pady=(14, 6))
        tk.Label(log_frame, text="TRAFFIC", font=self.f_mono_s, fg=DIM, bg=INK).pack(anchor="w")
        self.log = tk.Text(log_frame, height=8, bg=PANEL, fg=TEXT, font=self.f_mono,
                           relief="flat", state="disabled", padx=10, pady=8)
        self.log.pack(fill="both", pady=(4, 0))
        self.log.tag_configure("in",  foreground=TEXT)
        self.log.tag_configure("ok",  foreground=OK_COLOR)
        self.log.tag_configure("err", foreground=ERR_COLOR)
        self.log.tag_configure("sys", foreground=DIM)

        # footer
        hint = 'test:  printf \'{"cmd":"set","cell":4,"mark":"X"}\\n\' | nc 127.0.0.1 %d' % port
        tk.Label(self, text=hint, font=self.f_mono_s, fg=DIM, bg=INK).pack(anchor="w",
                                                                            padx=22, pady=(0, 16))

    def _draw_grid(self):
        M, C = self.M, self.C
        for i in (1, 2):
            p = M + i * C
            self.board.create_line(p, M, p, M + 3 * C, fill=GRID, width=4)
            self.board.create_line(M, p, M + 3 * C, p, fill=GRID, width=4)
        self.board.create_rectangle(M, M, M + 3 * C, M + 3 * C, outline=GRID, width=2)
        for cell in range(9):                    # tiny cell numbers, as a hint
            x, y = self._cell_origin(cell)
            self.board.create_text(x + 7, y + 4, text=str(cell), anchor="nw",
                                   font=self.f_cellnum, fill=DIM)

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 2)
        self.geometry(f"+{x}+{y}")
        self.resizable(False, False)

    # ── inbox bridge ──

    def _poll_inbox(self):
        try:
            while True:
                msg = self.inbox.get_nowait()
                kind = msg[0]
                if kind == "connect":
                    self.clients += 1
                    self.clients_lbl.configure(text=f"clients connected: {self.clients}")
                    self._log(f"── client connected: {msg[1]} ──\n", "sys")
                elif kind == "disconnect":
                    self.clients = max(0, self.clients - 1)
                    self.clients_lbl.configure(text=f"clients connected: {self.clients}")
                    self._log(f"── client disconnected: {msg[1]} ──\n", "sys")
                elif kind == "traffic":
                    _, raw, resp = msg
                    self._log("← " + raw.decode("utf-8", "replace") + "\n", "in")
                    good = resp.get("status") == "ok"
                    self._log("→ " + json.dumps(resp) + "\n", "ok" if good else "err")
                    if not good:
                        self._flash_error()
                elif kind == "apply":
                    self._apply(msg[1])
        except queue.Empty:
            pass
        self.after(60, self._poll_inbox)

    def _log(self, text, tag):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag)
        if int(self.log.index("end-1c").split(".")[0]) > 500:
            self.log.delete("1.0", "200.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ── board rendering ──

    def _apply(self, event):
        if event[0] == "reset":
            self._reset_board()
        else:
            _, cell, mark = event
            self._place(cell, mark)

    def _place(self, cell, mark):
        self._clear_cell(cell)
        self.cells[cell] = mark
        self.anim_token[cell] = object()         # cancels any running animation
        x, y = self._cell_origin(cell)
        box = (x + self.PAD, y + self.PAD,
               x + self.C - self.PAD, y + self.C - self.PAD)
        if mark == "X":
            self._anim_x(cell, box, self.anim_token[cell], 0)
        else:
            self._anim_o(cell, box, self.anim_token[cell], 0)
        self._ring(cell, mark)

    def _anim_x(self, cell, box, token, step, N=9):
        if token is not self.anim_token[cell]:
            return
        x0, y0, x1, y1 = box
        if step == 0:
            self.mark_ids[cell] = [
                self.board.create_line(x0, y0, x0, y0, fill=X_COLOR,
                                       width=self.STROKE, capstyle="round"),
                self.board.create_line(x0, y1, x0, y1, fill=X_COLOR,
                                       width=self.STROKE, capstyle="round"),
            ]
        t = (step + 1) / N
        a, b = self.mark_ids[cell]
        self.board.coords(a, x0, y0, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        self.board.coords(b, x0, y1, x0 + (x1 - x0) * t, y1 + (y0 - y1) * t)
        if step + 1 < N:
            self.after(18, lambda: self._anim_x(cell, box, token, step + 1, N))

    def _anim_o(self, cell, box, token, step, N=14):
        if token is not self.anim_token[cell]:
            return
        if step == 0:
            self.mark_ids[cell] = [
                self.board.create_arc(*box, start=90, extent=1, style="arc",
                                      outline=O_COLOR, width=self.STROKE)
            ]
        self.board.itemconfigure(self.mark_ids[cell][0],
                                 extent=max(1, round(360 * (step + 1) / N)))
        if step + 1 < N:
            self.after(18, lambda: self._anim_o(cell, box, token, step + 1, N))

    def _ring(self, cell, mark):
        if self.last_ring is not None:
            self.board.delete(self.last_ring)
        x, y = self._cell_origin(cell)
        self.last_ring = self.board.create_rectangle(
            x + 6, y + 6, x + self.C - 6, y + self.C - 6,
            outline=X_COLOR if mark == "X" else O_COLOR, width=2)

    def _clear_cell(self, cell):
        if self.mark_ids[cell]:
            for item in self.mark_ids[cell]:
                self.board.delete(item)
        self.mark_ids[cell] = None
        self.cells[cell] = None
        self.anim_token[cell] = object()

    def _reset_board(self):
        for cell in range(9):
            self._clear_cell(cell)
        if self.last_ring is not None:
            self.board.delete(self.last_ring)
            self.last_ring = None
        self.board.configure(bg="#123138")       # short flash as feedback
        self.after(130, lambda: self.board.configure(bg=BOARD_BG))

    # ── small life signs ──

    def _pulse(self):
        self._tick += 1
        if not self._error_shown:
            self.dot.configure(fg=O_COLOR if self._tick % 2 else "#2b8f83")
        self.after(700, self._pulse)

    def _flash_error(self):
        self._error_shown = True
        self.dot.configure(fg=ERR_COLOR)
        self.after(450, self._clear_error)

    def _clear_error(self):
        self._error_shown = False

    # ── hover highlight (display only — clicking does nothing) ──

    def _cell_origin(self, cell):
        return (self.M + (cell % 3) * self.C, self.M + (cell // 3) * self.C)

    def _cell_at(self, x, y):
        col, row = (x - self.M) // self.C, (y - self.M) // self.C
        return row * 3 + col if 0 <= col < 3 and 0 <= row < 3 else None

    def _on_motion(self, ev):
        cell = self._cell_at(ev.x, ev.y)
        if cell is None:
            self._hide_hover()
            return
        x, y = self._cell_origin(cell)
        self.board.coords(self.hover_id, x + 2, y + 2, x + self.C - 2, y + self.C - 2)

    def _on_leave(self, _ev):
        self._hide_hover()

    def _hide_hover(self):
        self.board.coords(self.hover_id, -10, -10, -10, -10)


# ── entry point ──────────────────────────────────────────────────────────

def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            sys.exit(f"usage: python {sys.argv[0]} [port]")

    inbox = queue.Queue()
    try:
        server = BoardServer(HOST, port, inbox)
    except OSError as exc:
        sys.exit(f"cannot bind {HOST}:{port} ({exc}) — is another instance running?")

    threading.Thread(target=server.serve_forever, daemon=True).start()
    App(HOST, port, inbox).mainloop()


if __name__ == "__main__":
    main()