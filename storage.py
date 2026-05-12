"""Block-level storage abstraction — in-memory byte array."""

BLOCK_SIZE = 512


class Storage:
    def __init__(self, total_blocks: int):
        self.total_blocks = total_blocks
        self._data = bytearray(total_blocks * BLOCK_SIZE)

    def read_block(self, bno: int) -> bytearray:
        if bno < 0 or bno >= self.total_blocks:
            raise IndexError(f"Block {bno} out of range (0..{self.total_blocks-1})")
        off = bno * BLOCK_SIZE
        return bytearray(self._data[off: off + BLOCK_SIZE])

    def write_block(self, bno: int, data: bytes | bytearray):
        if bno < 0 or bno >= self.total_blocks:
            raise IndexError(f"Block {bno} out of range")
        if len(data) != BLOCK_SIZE:
            raise ValueError(f"Block data must be {BLOCK_SIZE} bytes, got {len(data)}")
        off = bno * BLOCK_SIZE
        self._data[off: off + BLOCK_SIZE] = data
