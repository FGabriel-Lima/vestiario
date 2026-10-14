"""Minimal CRI CPK reader (TOC only, no CRILAYLA). Usage: python -m vestiario.cpk <file.cpk> [substring-to-extract outdir]"""
import struct, sys, os

def utf_table(buf):
    assert buf[:4] == b"@UTF", buf[:4]
    b = buf[8:]
    _, rows_off, str_off, data_off, _, ncols, row_w, nrows = struct.unpack_from(">HHIIIHHI", b, 0)
    cstr = lambda o: b[str_off + o:b.index(b"\0", str_off + o)].decode("utf8", "replace")
    sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 9: 8, 0xA: 4, 0xB: 8}
    fmts = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "Q", 7: "q", 8: "f", 9: "d"}

    def read(t, pos):
        if t == 0xA: return cstr(struct.unpack_from(">I", b, pos)[0])
        if t == 0xB:
            o, n = struct.unpack_from(">II", b, pos)
            return b[data_off + o:data_off + o + n]
        return struct.unpack_from(">" + fmts[t], b, pos)[0]

    cols, pos = [], 24
    for _ in range(ncols):
        flags = b[pos]; name = cstr(struct.unpack_from(">I", b, pos + 1)[0]); pos += 5
        st, t = flags & 0xF0, flags & 0x0F
        const = None
        if st == 0x30:
            const = read(t, pos); pos += sizes[t]
        cols.append((name, st, t, const))
    rows = []
    for r in range(nrows):
        p, row = rows_off + r * row_w, {}
        for name, st, t, const in cols:
            if st == 0x50:
                row[name] = read(t, p); p += sizes[t]
            elif st == 0x30:
                row[name] = const
        rows.append(row)
    return rows

def toc(f):
    f.seek(0); hdr = f.read(0x800)
    assert hdr[:4] == b"CPK ", hdr[:4]
    h = utf_table(hdr[16:])[0]
    f.seek(h["TocOffset"]); t = f.read(16)
    assert t[:4] == b"TOC ", t[:4]
    size = struct.unpack_from("<Q", t, 8)[0]
    files = utf_table(f.read(size))
    base = min(h["TocOffset"], h.get("ContentOffset") or h["TocOffset"])
    for e in files:
        e["path"] = (e.get("DirName") or "") + "/" + e["FileName"]
        e["abs"] = base + e["FileOffset"]
    return files

if __name__ == "__main__":
    with open(sys.argv[1], "rb") as f:
        files = toc(f)
        want = sys.argv[2] if len(sys.argv) > 2 else None
        for e in files:
            if want is None:
                print(e["path"], e["FileSize"], e.get("ExtractSize"))
            elif want.lower() in e["path"].lower():
                f.seek(e["abs"]); blob = f.read(e["FileSize"])
                out = os.path.join(sys.argv[3], e["path"].replace("/", "_"))
                open(out, "wb").write(blob)
                print("extracted", e["path"], len(blob), "compressed" if e["FileSize"] != e.get("ExtractSize", e["FileSize"]) else "")
