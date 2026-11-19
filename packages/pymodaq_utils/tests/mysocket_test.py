import pytest

from pymodaq_utils.mysocket import Socket


class FakeSocket:
    """Fake socket returning pre-defined chunks, then b'' (peer closed)."""

    def __init__(self, chunks):
        self.chunks = list(chunks)

    def recv(self, n):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) > n:
            self.chunks.insert(0, chunk[n:])
            chunk = chunk[:n]
        return chunk


class TestCheckReceivedLength:
    def test_chunked_happy_path(self):
        payload = bytes(range(256)) * 40  # 10240 bytes, more than one 4096 read
        chunks = [payload[i : i + 1000] for i in range(0, len(payload), 1000)]
        sock = Socket(FakeSocket(chunks))
        assert sock.check_received_length(len(payload)) == payload

    def test_peer_closed_raises(self):
        sock = Socket(FakeSocket([b"abc", b"de"]))
        with pytest.raises(ConnectionError, match="5 bytes out of 10"):
            sock.check_received_length(10)

    def test_peer_closed_immediately_raises(self):
        sock = Socket(FakeSocket([]))
        with pytest.raises(ConnectionError):
            sock.check_received_length(1)

    def test_length_not_int(self):
        with pytest.raises(TypeError):
            Socket(FakeSocket([])).check_received_length("3")
