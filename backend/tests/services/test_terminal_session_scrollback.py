"""Tests for TerminalSession scrollback ring buffer."""

import threading
from collections import deque

from app.services.terminal_manager import TerminalSession


def _bare_session() -> TerminalSession:
    """Build a TerminalSession without triggering its background spawn.

    Used for testing scrollback methods in isolation — no real PTY is
    created and no thread is started."""
    sess = TerminalSession.__new__(TerminalSession)
    sess._scrollback = deque()
    sess._scrollback_bytes = 0
    sess._scrollback_seq = 0
    sess._scrollback_lock = threading.Lock()
    return sess


def test_scrollback_starts_empty():
    sess = _bare_session()
    data, seq = sess.get_scrollback()
    assert data == b""
    assert seq == 0


def test_append_scrollback_returns_recent_bytes_in_order():
    sess = _bare_session()
    sess.append_scrollback(b"hello ")
    sess.append_scrollback(b"world\n")
    data, seq = sess.get_scrollback()
    assert data == b"hello world\n"
    assert seq == 2


def test_append_scrollback_evicts_oldest_when_over_cap():
    sess = _bare_session()
    original_cap = TerminalSession.SCROLLBACK_MAX_BYTES
    TerminalSession.SCROLLBACK_MAX_BYTES = 10
    try:
        sess.append_scrollback(b"AAAAA")  # 5 bytes, seq 1
        sess.append_scrollback(b"BBBBB")  # 5 bytes, total 10, seq 2
        sess.append_scrollback(b"CCCCC")  # 5 bytes -> trims 5 oldest -> total still 10, seq 3
        data, seq = sess.get_scrollback()
        # Oldest 5 ("AAAAA") were evicted; remainder = "BBBBBCCCCC"
        assert data == b"BBBBBCCCCC"
        assert seq == 3
    finally:
        TerminalSession.SCROLLBACK_MAX_BYTES = original_cap


def test_get_scrollback_returns_full_concatenation():
    sess = _bare_session()
    for i in range(50):
        sess.append_scrollback(f"{i:04d}".encode())
    data, seq = sess.get_scrollback()
    # 50 chunks of 4 bytes = 200 bytes
    assert len(data) == 200
    assert seq == 50
    assert data[:8] == b"00000001"
    assert data[-4:] == b"0049"


def test_append_scrollback_is_thread_safe():
    """Many threads appending concurrently must not corrupt the buffer."""
    import concurrent.futures

    sess = _bare_session()
    chunk = b"x" * 100  # 100 bytes per call
    n_threads = 10
    calls_per_thread = 100

    def worker():
        for _ in range(calls_per_thread):
            sess.append_scrollback(chunk)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as ex:
        list(ex.map(lambda _: worker(), range(n_threads)))

    data, seq = sess.get_scrollback()
    expected_bytes = n_threads * calls_per_thread * len(chunk)
    # Cap is 256 KB; expected bytes are 100*1000 = 100_000 (under cap).
    assert seq == n_threads * calls_per_thread
    assert len(data) == expected_bytes
    assert data == chunk * (n_threads * calls_per_thread)