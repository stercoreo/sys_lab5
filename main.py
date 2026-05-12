import sys
from storage import Storage
from fs import FS

TOTAL_BLOCKS = 256
NUM_INODES = 64


def demo(fs: FS):
    print("=== Lab 5 Demo ===\n")

    print("[mkfs] Creating filesystem...")
    fs.mkfs(TOTAL_BLOCKS, NUM_INODES)
    print(f"[pwd] CWD = {fs.cwd}")

    print("\n[mkdir] Creating directory tree /home/user/docs ...")
    fs.mkdir("/home")
    fs.mkdir("/home/user")
    fs.mkdir("/home/user/docs")
    fs.mkdir("/tmp")

    print("[create] /home/user/docs/readme.txt")
    fs.create("/home/user/docs/readme.txt")
    fs.write("/home/user/docs/readme.txt", 0, "Hello from Lab 5!\n")

    print("\n[symlink] /home/user/link_to_docs -> /home/user/docs")
    fs.symlink("/home/user/docs", "/home/user/link_to_docs")

    print("[ls /home/user]:")
    for line in fs.ls("/home/user"):
        print("  ", line)

    print("\n[read via symlink] /home/user/link_to_docs/readme.txt:")
    data = fs.read("/home/user/link_to_docs/readme.txt", 0, 100)
    print("  " + repr(data))

    print("\n[stat] symlink itself:")
    print("  " + fs.stat("/home/user/link_to_docs"))

    print("\n[cd] Changing directory to /home/user...")
    fs.cd("/home/user")
    print(f"[pwd] CWD = {fs.cwd}")

    print("\n[ls .] (relative path from CWD):")
    for line in fs.ls("."):
        print("  ", line)

    print("\n[create] relative path: docs/notes.txt")
    fs.create("docs/notes.txt")
    fs.write("docs/notes.txt", 0, "Relative write works!\n")
    print("[read] docs/notes.txt:", repr(fs.read("docs/notes.txt", 0, 100)))

    print("\n[symlink] /tmp/shortcut -> /home/user/docs (absolute target)")
    fs.symlink("/home/user/docs", "/tmp/shortcut")

    print("[ls /tmp]:")
    for line in fs.ls("/tmp"):
        print("  ", line)

    print("\n[stat via symlink chain] /tmp/shortcut/readme.txt:")
    print("  " + fs.stat("/tmp/shortcut/readme.txt"))

    print("\n[mkdir + rmdir] /tmp/to_delete...")
    fs.mkdir("/tmp/to_delete")
    print("[ls /tmp before rmdir]:", [e.split("\t")[0].strip() for e in fs.ls("/tmp")])
    fs.rmdir("/tmp/to_delete")
    print("[ls /tmp after rmdir]:", [e.split("\t")[0].strip() for e in fs.ls("/tmp")])

    print("\n[cd ..] Going up...")
    fs.cd("..")
    print(f"[pwd] CWD = {fs.cwd}")

    print("\n[unlink symlink] /home/user/link_to_docs...")
    fs.unlink("/home/user/link_to_docs")
    print("[ls /home/user after unlink]:")
    for line in fs.ls("/home/user"):
        print("  ", line)

    print("\n=== Demo complete ===")


def interactive(fs: FS):
    initialized = False
    print("\nLab 5 Filesystem Shell. Type 'help' for commands.")
    while True:
        try:
            cwd = fs.cwd if initialized else "/"
            line = input(f"fs:{cwd}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split(maxsplit=3)
        cmd = parts[0].lower()

        try:
            if cmd in ("exit", "quit"):
                break
            elif cmd == "mkfs":
                total = int(parts[1]) if len(parts) > 1 else TOTAL_BLOCKS
                inodes = int(parts[2]) if len(parts) > 2 else NUM_INODES
                fs.mkfs(total, inodes)
                initialized = True
                print(f"mkfs: {total} blocks, {inodes} inodes")
            elif not initialized:
                print("Run 'mkfs' first.")
            elif cmd == "pwd":
                print(fs.cwd)
            elif cmd == "cd":
                path = parts[1] if len(parts) > 1 else "/"
                fs.cd(path)
            elif cmd == "stat":
                print(fs.stat(parts[1]))
            elif cmd == "ls":
                path = parts[1] if len(parts) > 1 else "."
                for entry in fs.ls(path):
                    print(" ", entry)
            elif cmd == "mkdir":
                fs.mkdir(parts[1])
                print(f"mkdir: {parts[1]}")
            elif cmd == "rmdir":
                fs.rmdir(parts[1])
                print(f"rmdir: {parts[1]}")
            elif cmd == "create":
                ino = fs.create(parts[1])
                print(f"create: {parts[1]} (ino={ino})")
            elif cmd == "write":
                path, offset, data = parts[1], int(parts[2]), parts[3]
                n = fs.write(path, offset, data.encode().decode("unicode_escape").encode())
                print(f"write: {n} bytes written")
            elif cmd == "read":
                path, offset, length = parts[1], int(parts[2]), int(parts[3])
                print(repr(fs.read(path, offset, length)))
            elif cmd == "link":
                fs.link(parts[1], parts[2])
                print(f"link: {parts[1]} -> {parts[2]}")
            elif cmd == "unlink":
                fs.unlink(parts[1])
                print(f"unlink: {parts[1]}")
            elif cmd == "symlink":
                fs.symlink(parts[1], parts[2])
                print(f"symlink: {parts[2]} -> {parts[1]}")
            elif cmd == "truncate":
                fs.truncate(parts[1], int(parts[2]))
                print(f"truncate: {parts[1]} -> {parts[2]} bytes")
            else:
                print(f"Unknown command: {cmd}")
        except Exception as e:
            print(f"Error: {e}")


def main():
    storage = Storage(total_blocks=TOTAL_BLOCKS)
    fs = FS(storage)

    demo(fs)
    print()
    interactive(fs)


if __name__ == "__main__":
    main()
