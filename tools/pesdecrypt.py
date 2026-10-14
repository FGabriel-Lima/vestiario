"""Port of pesXdecrypter (public domain) for PES 2021 saves. Usage: pesdecrypt.py <in> <outdir>"""
import random, struct, sys, os

KEY21 = bytes.fromhex(
    "9061D866437724F892BAB87121C76063F0919A7DED4780DE51F5DDD108FE3284"
    "F5099200B23E889FEB244305587600229BFEECF6500029D3427550B9ECD2F675")
M = 0xFFFFFFFF

def mt_from_array(words):
    # init_genrand(19650218) + init_by_array, as in mt19937ar.c
    mt = [0] * 624
    mt[0] = 19650218
    for i in range(1, 624):
        mt[i] = (1812433253 * (mt[i-1] ^ (mt[i-1] >> 30)) + i) & M
    i, j, n = 1, 0, len(words)
    for _ in range(max(624, n)):
        mt[i] = ((mt[i] ^ ((mt[i-1] ^ (mt[i-1] >> 30)) * 1664525)) + words[j] + j) & M
        i += 1; j += 1
        if i >= 624: mt[0] = mt[623]; i = 1
        if j >= n: j = 0
    for _ in range(623):
        mt[i] = ((mt[i] ^ ((mt[i-1] ^ (mt[i-1] >> 30)) * 1566083941)) - i) & M
        i += 1
        if i >= 624: mt[0] = mt[623]; i = 1
    mt[0] = 0x80000000
    r = random.Random()
    r.setstate((3, tuple(mt) + (624,), None))
    return lambda: r.getrandbits(32)

rol = lambda a, s: ((a << s) | (a >> (32 - s))) & M
ror = lambda a, s: ((a >> s) | (a << (32 - s))) & M

def crypt_stream(key, data):
    rnd = mt_from_array(struct.unpack("<16I", key))
    c0, c1, c2, c3 = rnd(), rnd(), rnd(), rnd()
    n = len(data) // 4
    words = struct.unpack(f"<{n}I", data[:n*4])
    out = []
    for w in words:
        c4 = rnd()
        out.append(c4 ^ c3 ^ c2 ^ c1 ^ c0 ^ w)
        c0, c1, c2, c3 = ror(c1, 15), rol(c2, 11), rol(c3, 7), ror(c4, 13)
    res = bytearray(struct.pack(f"<{n}I", *out))
    if len(data) & 3:
        tail = data[n*4:] + b"\0" * (4 - (len(data) & 3))
        rest = struct.unpack("<I", tail)[0] ^ rnd() ^ c3 ^ c2 ^ c1 ^ c0
        res += struct.pack("<I", rest)[:len(data) & 3]
    return bytes(res)

def xor_long(key, p):
    return b"".join(struct.pack("<Q", struct.unpack_from("<Q", key, i*8)[0] ^ p) for i in range(8))

def decrypt(raw, master=KEY21):
    shuffled = b"".join(master[i*8:i*8+8][::-1] for i in range(8))
    hkey = bytes(a ^ b for a, b in zip(raw[256:320], shuffled))
    enc_header = crypt_stream(hkey, raw[:320])[:256] + raw[256:320]
    rolling = bytearray(enc_header[:64])
    for i, b in enumerate(enc_header[64:320]):
        rolling[i & 63] ^= b
    pos, HS = 320, 208
    hdr = crypt_stream(xor_long(rolling, HS), raw[pos:pos+HS]); pos += HS
    data_size, logo_size, desc_size, serial_len = struct.unpack_from("<4I", hdr, 64)
    parts = {"header.dat": hdr}
    for idx, (name, size) in enumerate([("description.dat", desc_size), ("logo.png", logo_size),
                                         ("data.dat", data_size), ("version.txt", serial_len*2)]):
        parts[name] = crypt_stream(xor_long(rolling, idx), raw[pos:pos+size]); pos += size
    return parts

if __name__ == "__main__":
    raw = open(sys.argv[1], "rb").read()
    os.makedirs(sys.argv[2], exist_ok=True)
    for name, blob in decrypt(raw).items():
        open(os.path.join(sys.argv[2], name), "wb").write(blob)
        print(name, len(blob))
