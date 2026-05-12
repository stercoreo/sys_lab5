import struct
from storage import Storage, BLOCK_SIZE

T_FREE = 0
T_FILE = 1
T_DIR = 2
T_SYMLINK = 3

INODE_SIZE = 64
INODES_PER_BLOCK = BLOCK_SIZE // INODE_SIZE
INDIRECT_PTRS = BLOCK_SIZE // 4

_INODE_FMT = struct.Struct("<BxHI12II4x")
assert _INODE_FMT.size == INODE_SIZE


class Inode:
    def __init__(self):
        self.itype: int = T_FREE
        self.nlink: int = 0
        self.size: int = 0
        self.direct: list[int] = [0] * 12
        self.indirect: int = 0

    @classmethod
    def from_bytes(cls, data: bytes | bytearray) -> "Inode":
        fields = _INODE_FMT.unpack_from(data)
        ino = cls()
        ino.itype = fields[0]
        ino.nlink = fields[1]
        ino.size = fields[2]
        ino.direct = list(fields[3:15])
        ino.indirect = fields[15]
        return ino

    def to_bytes(self) -> bytes:
        return _INODE_FMT.pack(
            self.itype, self.nlink, self.size,
            *self.direct,
            self.indirect,
        )


class InodeTable:
    def __init__(self, storage: Storage, inode_start: int, num_inodes: int):
        self._storage = storage
        self._start = inode_start
        self._num = num_inodes

    def read(self, ino: int) -> Inode:
        if not (0 <= ino < self._num):
            raise ValueError(f"Inode {ino} out of range")
        blk = self._start + ino // INODES_PER_BLOCK
        off = (ino % INODES_PER_BLOCK) * INODE_SIZE
        buf = self._storage.read_block(blk)
        return Inode.from_bytes(buf[off: off + INODE_SIZE])

    def write(self, ino: int, inode: Inode):
        if not (0 <= ino < self._num):
            raise ValueError(f"Inode {ino} out of range")
        blk = self._start + ino // INODES_PER_BLOCK
        off = (ino % INODES_PER_BLOCK) * INODE_SIZE
        buf = self._storage.read_block(blk)
        buf[off: off + INODE_SIZE] = inode.to_bytes()
        self._storage.write_block(blk, buf)

    def alloc(self) -> int:
        for i in range(1, self._num):
            ino = self.read(i)
            if ino.itype == T_FREE:
                return i
        raise OSError("No free inodes")
