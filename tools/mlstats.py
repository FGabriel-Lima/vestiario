"""Season stats for one club from a decrypted ML data.dat. Usage: mlstats.py <data.dat> <Player.raw> <team name>"""
import sys, struct, collections
sys.stdout.reconfigure(encoding="utf-8")

d = open(sys.argv[1], "rb").read()
p = open(sys.argv[2], "rb").read()
PR = 312
names = {struct.unpack_from("<I", p, k*PR + 8)[0]: p[k*PR + 68:p.index(b"\0", k*PR + 68)].decode("utf8", "replace")
         for k in range(len(p) // PR)}

cstr = lambda o: d[o:d.index(b"\0", o)].decode("utf8", "replace")
TEAM0, TEAMSZ = 84, 1680                       # team table: name at +0 of each 1680-byte record
teams = {}
i = 0
while TEAM0 + i*TEAMSZ < 1194600:
    if d[TEAM0 + i*TEAMSZ]: teams[i] = cstr(TEAM0 + i*TEAMSZ)
    i += 1
me = next(k for k, v in teams.items() if v == sys.argv[3])

MATCH0, MSZ, SLOTS = 3316488, 596, 17          # ponytail: offsets found by hand for this save; detect dynamically before reuse
stats = collections.defaultdict(lambda: [0, 0, 0])   # pid -> [jogos, gols, assist]
results = []
h = MATCH0
while d[h+1] == 7 and d[h] in (0xe8, 0xe9, 0xea):
    year, month, day = struct.unpack_from("<HBB", d, h)
    home, away = (struct.unpack_from("<H", d, h + o)[0] & 0x3FFF for o in (12, 16))
    if me in (home, away):
        side = 0 if home == me else 1
        g = [0, 0]
        for s in range(2 * SLOTS):
            slot, pid, x = struct.unpack_from("<III", d, h + 28 + s*16)
            if slot == 0xFFFF: continue
            g[s // SLOTS] += x & 0xFF
            if s // SLOTS == side:
                st = stats[pid & 0x7FFFFFFF]
                st[0] += 1; st[1] += x & 0xFF; st[2] += (x >> 8) & 0xFF
        results.append(f"{day:02}/{month:02}/{year}  {teams.get(home, home)} {g[0]} x {g[1]} {teams.get(away, away)}")
    h += MSZ

print(f"{len(results)} partidas de {teams[me]}\n")
print("\n".join(results))
print(f"\n{'Jogador':<24}{'J':>4}{'G':>4}{'A':>4}")
for pid, (j, gl, a) in sorted(stats.items(), key=lambda kv: (-kv[1][1], -kv[1][2], -kv[1][0])):
    print(f"{names.get(pid, pid):<24}{j:>4}{gl:>4}{a:>4}")
