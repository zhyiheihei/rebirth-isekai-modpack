"""生成 Minecraft 的 servers.dat（未压缩 NBT），让多人列表里预置服务器。

26.x 的 servers.dat 是裸 NBT：根 TAG_Compound，内含 TAG_List("servers")，
每个元素是 {name, ip, hidden?, icon?}。
"""
import struct

TAG_END = 0
TAG_INT = 3
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10


def _u16(n):
    return struct.pack(">H", n)


def _i32(n):
    return struct.pack(">i", n)


def _str(value):
    data = value.encode("utf-8")
    return _u16(len(data)) + data


def _named(tag, name, payload):
    return bytes([tag]) + _str(name) + payload


def _compound(pairs):
    body = b"".join(_named(t, n, p) for t, n, p in pairs)
    return body + bytes([TAG_END])


def _server(srv):
    pairs = [
        (TAG_STRING, "name", _str(srv["name"])),
        (TAG_STRING, "ip", _str(srv["ip"])),
        (TAG_INT, "hidden", _i32(1 if srv.get("hidden") else 0)),
    ]
    if srv.get("icon"):
        pairs.append((TAG_STRING, "icon", _str(srv["icon"])))
    return _compound(pairs)


def build(servers):
    items = b"".join(_server(s) for s in servers)
    list_payload = bytes([TAG_COMPOUND]) + _i32(len(servers)) + items
    root_payload = _named(TAG_LIST, "servers", list_payload)
    return bytes([TAG_COMPOUND]) + _u16(0) + root_payload + bytes([TAG_END])


def write(path, servers):
    with open(path, "wb") as f:
        f.write(build(servers))
