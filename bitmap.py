"""Block allocation bitmap — one bit per data block."""

from storage import Storage, BLOCK_SIZE


class Bitmap:
    def __init__(self, storage: Storage, bitmap_start: int, total_blocks: int):
        self._storage = storage
        self._start = bitmap_start
        self._total = total_blocks
        self._bits_per_block = BLOCK_SIZE * 8

    def _locate(self, bno: int) -> tuple[int, int, int]:
        """Return (block_number, byte_offset, bit_mask) for a given block index."""
        rel = bno
        blk = self._start + rel // self._bits_per_block
        byte = (rel % self._bits_per_block) // 8
        bit = rel % 8
        return blk, byte, (1 << bit)

    def is_free(self, bno: int) -> bool:
        blk, byte, mask = self._locate(bno)
        buf = self._storage.read_block(blk)
        return (buf[byte] & mask) == 0

    def _set(self, bno: int, value: bool):
        blk, byte, mask = self._locate(bno)
        buf = self._storage.read_block(blk)
        if value:
            buf[byte] |= mask
        else:
            buf[byte] &= ~mask & 0xFF
        self._storage.write_block(blk, buf)

    def alloc(self) -> int:
        """Allocate a free block; return its block number or raise OSError."""
        for bno in range(self._total):
            if self.is_free(bno):
                self._set(bno, True)
                return bno
        raise OSError("No free blocks")

    def free(self, bno: int):
        if not (0 <= bno < self._total):
            raise ValueError(f"Block {bno} out of range")
        self._set(bno, False)
