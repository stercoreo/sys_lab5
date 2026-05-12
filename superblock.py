"""Superblock — block 0, describes the filesystem layout."""

import struct
from storage import Storage, BLOCK_SIZE

MAGIC = 0x4D465301  # "MFS\x01"

# Layout: magic, block_size, total_blocks, num_inodes,
#         bitmap_start, inode_start, data_start, root_inode
_SB_FMT = struct.Struct("<8I")  # 32 bytes

# Number of blocks occupied by inode table
INODE_SIZE = 64  # bytes per inode


def _inode_blocks(num_inodes: int) -> int:
    inodes_per_block = BLOCK_SIZE // INODE_SIZE
    return (num_inodes + inodes_per_block - 1) // inodes_per_block


class Superblock:
    def __init__(self):
        self.magic: int = MAGIC
        self.block_size: int = BLOCK_SIZE
        self.total_blocks: int = 0
        self.num_inodes: int = 0
        self.bitmap_start: int = 0
        self.inode_start: int = 0
        self.data_start: int = 0
        self.root_inode: int = 0

    @classmethod
    def create(cls, total_blocks: int, num_inodes: int) -> "Superblock":
        sb = cls()
        sb.total_blocks = total_blocks
        sb.num_inodes = num_inodes
        sb.bitmap_start = 1  # block 0 = superblock
        bitmap_blocks = (total_blocks + BLOCK_SIZE * 8 - 1) // (BLOCK_SIZE * 8)
        sb.inode_start = sb.bitmap_start + bitmap_blocks
        sb.data_start = sb.inode_start + _inode_blocks(num_inodes)
        sb.root_inode = 0
        return sb

    def write(self, storage: Storage):
        buf = bytearray(BLOCK_SIZE)
        packed = _SB_FMT.pack(
            self.magic, self.block_size, self.total_blocks, self.num_inodes,
            self.bitmap_start, self.inode_start, self.data_start, self.root_inode,
        )
        buf[: len(packed)] = packed
        storage.write_block(0, buf)

    @classmethod
    def read(cls, storage: Storage) -> "Superblock":
        buf = storage.read_block(0)
        fields = _SB_FMT.unpack_from(buf)
        magic = fields[0]
        if magic != MAGIC:
            raise ValueError(f"Bad magic: 0x{magic:08X}, expected 0x{MAGIC:08X}")
        sb = cls()
        (sb.magic, sb.block_size, sb.total_blocks, sb.num_inodes,
         sb.bitmap_start, sb.inode_start, sb.data_start, sb.root_inode) = fields
        return sb
