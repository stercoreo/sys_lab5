"""Directory entry layout.

DirEntry (32 bytes):
  offset  0 (28B): name — null-terminated, UTF-8
  offset 28 (4B):  ino  — inode number (0 = free slot)
"""

import struct

MAX_NAME = 28
DIR_ENTRY_SIZE = 32

_DIR_FMT = struct.Struct("<28sI")
assert _DIR_FMT.size == DIR_ENTRY_SIZE


class DirEntry:
    def __init__(self, name: str = "", ino: int = 0):
        self.name = name
        self.ino = ino

    @property
    def is_free(self) -> bool:
        return self.ino == 0 and not self.name

    @classmethod
    def from_bytes(cls, data: bytes | bytearray) -> "DirEntry":
        raw_name, ino = _DIR_FMT.unpack_from(data)
        name = raw_name.rstrip(b"\x00").decode("utf-8", errors="replace")
        return cls(name, ino)

    def to_bytes(self) -> bytes:
        name_bytes = self.name.encode("utf-8")[:MAX_NAME]
        name_padded = name_bytes.ljust(MAX_NAME, b"\x00")
        return _DIR_FMT.pack(name_padded, self.ino)
