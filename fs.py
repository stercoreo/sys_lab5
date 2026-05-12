import struct
from storage import Storage, BLOCK_SIZE
from superblock import Superblock
from bitmap import Bitmap
from inode import Inode, InodeTable, T_FREE, T_FILE, T_DIR, T_SYMLINK, INDIRECT_PTRS
from dir_entry import DirEntry, DIR_ENTRY_SIZE, MAX_NAME

MAX_OPEN = 64
SYMLINK_MAX_DEPTH = 8
_PTR_FMT = struct.Struct("<I")


class FS:
    def __init__(self, storage: Storage):
        self._storage = storage
        self._sb: Superblock | None = None
        self._bitmap: Bitmap | None = None
        self._inodes: InodeTable | None = None
        self._open_table = [None] * MAX_OPEN
        self._cwd: int = 1

    def mkfs(self, total_blocks: int, num_inodes: int):
        sb = Superblock.create(total_blocks, num_inodes)
        sb.write(self._storage)
        self._mount()
        for _ in range(sb.data_start):
            self._bitmap.alloc()

        root_ino_idx = self._inodes.alloc()
        root_ino = Inode()
        root_ino.itype = T_DIR
        root_ino.nlink = 2
        self._inodes.write(root_ino_idx, root_ino)
        self._sb.root_inode = root_ino_idx
        self._sb.write(self._storage)

        self._dir_add(root_ino_idx, ".", root_ino_idx)
        self._dir_add(root_ino_idx, "..", root_ino_idx)
        self._cwd = root_ino_idx

    def mount(self):
        self._mount()

    def _mount(self):
        self._sb = Superblock.read(self._storage)
        self._bitmap = Bitmap(self._storage, self._sb.bitmap_start, self._sb.total_blocks)
        self._inodes = InodeTable(self._storage, self._sb.inode_start, self._sb.num_inodes)
        self._cwd = self._sb.root_inode

    @property
    def cwd(self) -> str:
        return self._abs_path_of(self._cwd)

    def cd(self, path: str):
        ino_idx, ino = self._resolve(path)
        if ino.itype != T_DIR:
            raise NotADirectoryError(f"'{path}' is not a directory")
        self._cwd = ino_idx

    def stat(self, path: str) -> str:
        ino_idx, ino = self._resolve_no_follow(path)
        type_map = {T_FILE: "file", T_DIR: "dir", T_SYMLINK: "symlink"}
        type_name = type_map.get(ino.itype, "unknown")
        extra = ""
        if ino.itype == T_SYMLINK:
            target = self._inode_read(ino, 0, ino.size).decode()
            extra = f"  target={target!r}"
        return (f"inode={ino_idx}  type={type_name}  nlink={ino.nlink}  "
                f"size={ino.size}{extra}")

    def ls(self, path: str = ".") -> list[str]:
        ino_idx, ino = self._resolve(path)
        if ino.itype != T_DIR:
            raise NotADirectoryError(f"'{path}' is not a directory")
        entries = self._dir_entries(ino_idx)
        result = []
        for e in entries:
            child = self._inodes.read(e.ino)
            type_map = {T_FILE: "-", T_DIR: "d", T_SYMLINK: "l"}
            t = type_map.get(child.itype, "?")
            suffix = ""
            if child.itype == T_SYMLINK:
                target = self._inode_read(child, 0, child.size).decode()
                suffix = f" -> {target}"
            result.append(f"{t}  {e.name}\t(ino={e.ino}){suffix}")
        return result

    def mkdir(self, path: str):
        parent_path, name = self._split_path(path)
        parent_idx, parent_ino = self._resolve(parent_path)
        if parent_ino.itype != T_DIR:
            raise NotADirectoryError(f"'{parent_path}' is not a directory")
        self._check_name_free(parent_idx, name)

        new_idx = self._alloc_inode(T_DIR)
        new_ino = self._inodes.read(new_idx)
        new_ino.nlink = 2
        self._inodes.write(new_idx, new_ino)

        self._dir_add(new_idx, ".", new_idx)
        self._dir_add(new_idx, "..", parent_idx)
        self._dir_add(parent_idx, name, new_idx)

        parent_ino = self._inodes.read(parent_idx)
        parent_ino.nlink += 1
        self._inodes.write(parent_idx, parent_ino)

    def rmdir(self, path: str):
        ino_idx, ino = self._resolve(path)
        if ino.itype != T_DIR:
            raise NotADirectoryError(f"'{path}' is not a directory")
        entries = self._dir_entries(ino_idx)
        non_special = [e for e in entries if e.name not in (".", "..")]
        if non_special:
            raise OSError(f"Directory '{path}' is not empty")

        parent_path, name = self._split_path(path)
        parent_idx, parent_ino = self._resolve(parent_path)
        self._dir_remove(parent_idx, name)

        self._free_inode_blocks(ino)
        ino.itype = T_FREE
        self._inodes.write(ino_idx, ino)

        parent_ino = self._inodes.read(parent_idx)
        parent_ino.nlink -= 1
        self._inodes.write(parent_idx, parent_ino)

    def create(self, path: str) -> int:
        parent_path, name = self._split_path(path)
        parent_idx, _ = self._resolve(parent_path)
        self._check_name_free(parent_idx, name)
        new_idx = self._alloc_inode(T_FILE)
        self._dir_add(parent_idx, name, new_idx)
        return new_idx

    def symlink(self, target: str, link_path: str):
        parent_path, name = self._split_path(link_path)
        parent_idx, _ = self._resolve(parent_path)
        self._check_name_free(parent_idx, name)

        new_idx = self._alloc_inode(T_SYMLINK)
        target_bytes = target.encode()
        ino = self._inodes.read(new_idx)
        self._inode_write(new_idx, ino, 0, target_bytes)
        self._dir_add(parent_idx, name, new_idx)

    def write(self, path: str, offset: int, data: bytes | str) -> int:
        if isinstance(data, str):
            data = data.encode()
        ino_idx, ino = self._resolve(path)
        if ino.itype != T_FILE:
            raise IsADirectoryError(f"'{path}' is not a regular file")
        return self._inode_write(ino_idx, ino, offset, data)

    def read(self, path: str, offset: int, length: int) -> bytes:
        ino_idx, ino = self._resolve(path)
        if ino.itype != T_FILE:
            raise IsADirectoryError(f"'{path}' is not a regular file")
        return self._inode_read(ino, offset, length)

    def link(self, src: str, dst: str):
        src_idx, src_ino = self._resolve(src)
        if src_ino.itype == T_DIR:
            raise IsADirectoryError("Cannot hard-link a directory")
        parent_path, name = self._split_path(dst)
        parent_idx, _ = self._resolve(parent_path)
        self._check_name_free(parent_idx, name)
        self._dir_add(parent_idx, name, src_idx)
        src_ino.nlink += 1
        self._inodes.write(src_idx, src_ino)

    def unlink(self, path: str):
        parent_path, name = self._split_path(path)
        if name in (".", ".."):
            raise ValueError("Cannot unlink '.' or '..'")
        parent_idx, _ = self._resolve(parent_path)
        ino_idx = self._dir_lookup(parent_idx, name)
        if ino_idx is None:
            raise FileNotFoundError(f"'{path}' not found")
        ino = self._inodes.read(ino_idx)
        if ino.itype == T_DIR:
            raise IsADirectoryError("Use rmdir for directories")
        self._dir_remove(parent_idx, name)
        ino.nlink -= 1
        if ino.nlink == 0:
            self._free_inode_blocks(ino)
            ino.itype = T_FREE
        self._inodes.write(ino_idx, ino)

    def truncate(self, path: str, new_size: int):
        ino_idx, ino = self._resolve(path)
        if ino.itype != T_FILE:
            raise IsADirectoryError(f"'{path}' is not a regular file")
        if new_size == ino.size:
            return
        if new_size < ino.size:
            self._truncate_shrink(ino_idx, ino, new_size)
        else:
            ino.size = new_size
            self._inodes.write(ino_idx, ino)

    def _get_block_ptr(self, ino: Inode, logical_blk: int) -> int:
        if logical_blk < 12:
            return ino.direct[logical_blk]
        ind_idx = logical_blk - 12
        if ind_idx >= INDIRECT_PTRS:
            raise OSError("File too large")
        if ino.indirect == 0:
            return 0
        ind_buf = self._storage.read_block(ino.indirect)
        return _PTR_FMT.unpack_from(ind_buf, ind_idx * 4)[0]

    def _set_block_ptr(self, ino_idx: int, ino: Inode, logical_blk: int, bno: int):
        if logical_blk < 12:
            ino.direct[logical_blk] = bno
            self._inodes.write(ino_idx, ino)
        else:
            ind_idx = logical_blk - 12
            if ind_idx >= INDIRECT_PTRS:
                raise OSError("File too large")
            if ino.indirect == 0:
                ino.indirect = self._bitmap.alloc()
                self._storage.write_block(ino.indirect, bytearray(BLOCK_SIZE))
                self._inodes.write(ino_idx, ino)
            ind_buf = self._storage.read_block(ino.indirect)
            _PTR_FMT.pack_into(ind_buf, ind_idx * 4, bno)
            self._storage.write_block(ino.indirect, ind_buf)

    def _inode_write(self, ino_idx: int, ino: Inode, offset: int, data: bytes) -> int:
        written = 0
        pos = offset
        while written < len(data):
            blk_idx = pos // BLOCK_SIZE
            blk_off = pos % BLOCK_SIZE
            chunk = min(BLOCK_SIZE - blk_off, len(data) - written)
            bno = self._get_block_ptr(ino, blk_idx)
            if bno == 0:
                bno = self._bitmap.alloc()
                self._set_block_ptr(ino_idx, ino, blk_idx, bno)
                buf = bytearray(BLOCK_SIZE)
            else:
                buf = self._storage.read_block(bno)
            buf[blk_off: blk_off + chunk] = data[written: written + chunk]
            self._storage.write_block(bno, buf)
            written += chunk
            pos += chunk
        if pos > ino.size:
            ino.size = pos
            self._inodes.write(ino_idx, ino)
        return written

    def _inode_read(self, ino: Inode, offset: int, length: int) -> bytes:
        if offset >= ino.size:
            return b""
        length = min(length, ino.size - offset)
        result = bytearray()
        pos = offset
        remaining = length
        while remaining > 0:
            blk_idx = pos // BLOCK_SIZE
            blk_off = pos % BLOCK_SIZE
            chunk = min(BLOCK_SIZE - blk_off, remaining)
            bno = self._get_block_ptr(ino, blk_idx)
            if bno == 0:
                result.extend(b"\x00" * chunk)
            else:
                buf = self._storage.read_block(bno)
                result.extend(buf[blk_off: blk_off + chunk])
            pos += chunk
            remaining -= chunk
        return bytes(result)

    def _dir_entries(self, dir_ino_idx: int) -> list[DirEntry]:
        ino = self._inodes.read(dir_ino_idx)
        data = self._inode_read(ino, 0, ino.size)
        entries = []
        for i in range(0, len(data), DIR_ENTRY_SIZE):
            if i + DIR_ENTRY_SIZE > len(data):
                break
            entry = DirEntry.from_bytes(data[i: i + DIR_ENTRY_SIZE])
            if entry.name:
                entries.append(entry)
        return entries

    def _dir_lookup(self, dir_ino_idx: int, name: str) -> int | None:
        for entry in self._dir_entries(dir_ino_idx):
            if entry.name == name:
                return entry.ino
        return None

    def _dir_add(self, dir_ino_idx: int, name: str, ino: int):
        if len(name.encode()) > MAX_NAME:
            raise ValueError(f"Name '{name}' too long (max {MAX_NAME})")
        dir_ino = self._inodes.read(dir_ino_idx)
        data = self._inode_read(dir_ino, 0, dir_ino.size)
        for i in range(0, len(data), DIR_ENTRY_SIZE):
            slot = DirEntry.from_bytes(data[i: i + DIR_ENTRY_SIZE])
            if not slot.name:
                self._inode_write(dir_ino_idx, dir_ino, i, DirEntry(name, ino).to_bytes())
                return
        self._inode_write(dir_ino_idx, dir_ino, dir_ino.size, DirEntry(name, ino).to_bytes())

    def _dir_remove(self, dir_ino_idx: int, name: str):
        dir_ino = self._inodes.read(dir_ino_idx)
        data = self._inode_read(dir_ino, 0, dir_ino.size)
        for i in range(0, len(data), DIR_ENTRY_SIZE):
            slot = DirEntry.from_bytes(data[i: i + DIR_ENTRY_SIZE])
            if slot.name == name:
                self._inode_write(dir_ino_idx, dir_ino, i, DirEntry("", 0).to_bytes())
                return
        raise FileNotFoundError(f"'{name}' not found in directory")

    def _check_name_free(self, dir_ino_idx: int, name: str):
        if self._dir_lookup(dir_ino_idx, name) is not None:
            raise FileExistsError(f"'{name}' already exists")

    def _alloc_inode(self, itype: int) -> int:
        idx = self._inodes.alloc()
        ino = Inode()
        ino.itype = itype
        ino.nlink = 1
        self._inodes.write(idx, ino)
        return idx

    def _free_inode_blocks(self, ino: Inode):
        for bno in ino.direct:
            if bno:
                self._bitmap.free(bno)
        if ino.indirect:
            ind_buf = self._storage.read_block(ino.indirect)
            for i in range(INDIRECT_PTRS):
                bno = _PTR_FMT.unpack_from(ind_buf, i * 4)[0]
                if bno:
                    self._bitmap.free(bno)
            self._bitmap.free(ino.indirect)

    def _truncate_shrink(self, ino_idx: int, ino: Inode, new_size: int):
        old_last = (ino.size - 1) // BLOCK_SIZE if ino.size > 0 else -1
        new_last = (new_size - 1) // BLOCK_SIZE if new_size > 0 else -1
        for blk_idx in range(old_last, new_last, -1):
            bno = self._get_block_ptr(ino, blk_idx)
            if bno:
                self._bitmap.free(bno)
                self._set_block_ptr(ino_idx, ino, blk_idx, 0)
        ino.size = new_size
        self._inodes.write(ino_idx, ino)

    def _resolve(self, path: str, follow_depth: int = 0) -> tuple[int, Inode]:
        if follow_depth > SYMLINK_MAX_DEPTH:
            raise OSError(f"Symlink loop detected (depth > {SYMLINK_MAX_DEPTH})")

        if path == "" or path == ".":
            return self._cwd, self._inodes.read(self._cwd)

        if path.startswith("/"):
            cur_idx = self._sb.root_inode
        else:
            cur_idx = self._cwd

        parts = [p for p in path.split("/") if p]
        for part in parts:
            cur_ino = self._inodes.read(cur_idx)
            if cur_ino.itype == T_SYMLINK:
                target = self._inode_read(cur_ino, 0, cur_ino.size).decode()
                cur_idx, cur_ino = self._resolve(target, follow_depth + 1)
                if cur_ino.itype != T_DIR:
                    raise NotADirectoryError("Symlink target is not a directory")
            if cur_ino.itype != T_DIR:
                raise NotADirectoryError(f"Not a directory in path '{path}'")
            if part == ".":
                continue
            if part == "..":
                found = self._dir_lookup(cur_idx, "..")
                cur_idx = found if found is not None else cur_idx
                continue
            found = self._dir_lookup(cur_idx, part)
            if found is None:
                raise FileNotFoundError(f"'{part}' not found in path '{path}'")
            cur_idx = found

        ino = self._inodes.read(cur_idx)
        if ino.itype == T_SYMLINK:
            target = self._inode_read(ino, 0, ino.size).decode()
            return self._resolve(target, follow_depth + 1)
        return cur_idx, ino

    def _resolve_no_follow(self, path: str) -> tuple[int, Inode]:
        if path == "" or path == ".":
            return self._cwd, self._inodes.read(self._cwd)

        if path.startswith("/"):
            cur_idx = self._sb.root_inode
        else:
            cur_idx = self._cwd

        parts = [p for p in path.split("/") if p]
        for i, part in enumerate(parts):
            cur_ino = self._inodes.read(cur_idx)
            depth = 0
            while cur_ino.itype == T_SYMLINK:
                if depth > SYMLINK_MAX_DEPTH:
                    raise OSError("Symlink loop")
                target = self._inode_read(cur_ino, 0, cur_ino.size).decode()
                cur_idx, cur_ino = self._resolve(target)
                depth += 1
            if cur_ino.itype != T_DIR:
                raise NotADirectoryError(f"Not a directory in path '{path}'")

            if part == ".":
                continue
            if part == "..":
                found = self._dir_lookup(cur_idx, "..")
                cur_idx = found if found is not None else cur_idx
                continue
            found = self._dir_lookup(cur_idx, part)
            if found is None:
                raise FileNotFoundError(f"'{part}' not found in path '{path}'")
            cur_idx = found
        return cur_idx, self._inodes.read(cur_idx)

    def _split_path(self, path: str) -> tuple[str, str]:
        path = path.rstrip("/")
        if not path:
            return ".", "."
        idx = path.rfind("/")
        if idx < 0:
            return ".", path
        if idx == 0:
            return "/", path[1:]
        return path[:idx], path[idx + 1:]

    def _abs_path_of(self, ino_idx: int) -> str:
        if ino_idx == self._sb.root_inode:
            return "/"
        parts = []
        cur = ino_idx
        visited = set()
        while cur != self._sb.root_inode:
            if cur in visited:
                return "/(cycle)"
            visited.add(cur)
            parent = self._dir_lookup(cur, "..")
            if parent is None or parent == cur:
                break
            name = None
            for e in self._dir_entries(parent):
                if e.ino == cur and e.name not in (".", ".."):
                    name = e.name
                    break
            if name is None:
                break
            parts.append(name)
            cur = parent
        parts.reverse()
        return "/" + "/".join(parts)
