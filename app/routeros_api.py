"""عميل بسيط لـ MikroTik RouterOS API (المنفذ 8728) بدون مكتبات خارجية.
يدعم RouterOS 6.43 وما بعده (تسجيل الدخول المباشر)."""
import socket


class RouterOSError(Exception):
    pass


def encode_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return (n | 0x8000).to_bytes(2, "big")
    if n < 0x200000:
        return (n | 0xC00000).to_bytes(3, "big")
    if n < 0x10000000:
        return (n | 0xE0000000).to_bytes(4, "big")
    return b"\xf0" + n.to_bytes(4, "big")


class RouterOS:
    def __init__(self, host, port=8728, timeout=8):
        self.host, self.port, self.timeout = host, int(port), timeout
        self.sock = None

    # ---------- الاتصال ----------
    def connect(self, user, password):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.call("/login", {"name": user, "password": password})

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    # ---------- مستوى منخفض ----------
    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("انقطع الاتصال بالراوتر")
            buf += chunk
        return buf

    def _read_len(self):
        c = self._recv_exact(1)[0]
        if c & 0x80 == 0:
            return c
        if c & 0xC0 == 0x80:
            return ((c & 0x3F) << 8) | self._recv_exact(1)[0]
        if c & 0xE0 == 0xC0:
            return ((c & 0x1F) << 16) | int.from_bytes(self._recv_exact(2), "big")
        if c & 0xF0 == 0xE0:
            return ((c & 0x0F) << 24) | int.from_bytes(self._recv_exact(3), "big")
        return int.from_bytes(self._recv_exact(4), "big")

    def _send_word(self, w):
        b = w.encode("utf-8")
        self.sock.sendall(encode_len(len(b)) + b)

    def _read_sentence(self):
        words = []
        while True:
            n = self._read_len()
            if n == 0:
                return words
            words.append(self._recv_exact(n).decode("utf-8", "replace"))

    @staticmethod
    def _parse(words):
        d = {}
        for w in words:
            if w.startswith("="):
                k, _, v = w[1:].partition("=")
                d[k] = v
        return d

    # ---------- استدعاء الأوامر ----------
    def call(self, cmd, attrs=None, queries=None):
        """cmd مثل '/ip/hotspot/user/print'، attrs قاموس، queries قائمة مثل ['?name=abc']"""
        if not self.sock:
            raise ConnectionError("غير متصل بالراوتر")
        self._send_word(cmd)
        for k, v in (attrs or {}).items():
            self._send_word(f"={k}={v}")
        for q in queries or []:
            self._send_word(q)
        self._send_word("")
        results, error = [], None
        while True:
            s = self._read_sentence()
            if not s:
                continue
            kind = s[0]
            if kind == "!re":
                results.append(self._parse(s[1:]))
            elif kind == "!trap":
                error = self._parse(s[1:]).get("message", "خطأ غير معروف")
            elif kind == "!fatal":
                raise RouterOSError("خطأ فادح من الراوتر: " + " ".join(s[1:]))
            elif kind == "!done":
                break
        if error:
            raise RouterOSError(error)
        return results
