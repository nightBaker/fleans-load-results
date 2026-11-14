#!/usr/bin/env python3
"""Summarise /tmp/claude-0/work/results2/<scenario>-<label>/ (rest of the suite) as markdown."""
import os, re, statistics, collections, sys
R = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/work/results2'
L = ['net10', 'net11']


def rd(sc, lab, f):
    p = f'{R}/{sc}-{lab}/{f}'
    return open(p).read() if os.path.exists(p) else ''


def mib(s):
    m = re.match(r'([\d.]+)([KMG]i?B)', s)
    return float(m.group(1)) * {'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}.get(m.group(2), 1) if m else None


def cpu_mem(sc, lab, start_tag=None, end_tag=None):
    ph = {}
    for l in rd(sc, lab, 'phases.txt').splitlines():
        t, n = l.split(); ph[n] = int(t)
    t0 = ph.get(start_tag or 'start', 0); t1 = ph.get(end_tag or 'end', 1 << 40)
    snaps = collections.defaultdict(lambda: collections.defaultdict(float)); peak = collections.defaultdict(float)
    for l in rd(sc, lab, 'stats-timeline.txt').splitlines():
        p = l.split()
        if len(p) < 4 or not p[2].endswith('%'):
            continue
        try:
            t = int(p[0]); c = float(p[2].rstrip('%'))
        except ValueError:
            continue
        svc = re.sub(r'^fleans-load-|-\d+$', '', p[1]); v = mib(p[3])
        if v: peak[svc] = max(peak[svc], v)
        if t0 <= t <= t1:
            snaps[t][svc] += c; snaps[t]['total'] += c
            if re.match(r'fleans-|external-worker', svc): snaps[t]['fleans'] += c
    ks = sorted(snaps)
    avg = lambda s: statistics.mean(snaps[k].get(s, 0) for k in ks) if ks else None
    return dict(total=avg('total'), fleans=avg('fleans'), core=avg('fleans-core'), peak_core=peak.get('fleans-core'),
                peak_worker=peak.get('fleans-worker'), peak_api=peak.get('fleans-api'))


def k6metric(txt, name, field):
    m = re.search(rf'^\s*{re.escape(name)}\.*: (.*)$', txt, re.M)
    if not m:
        return None
    line = m.group(1)
    if field == 'rate%':
        mm = re.match(r'([\d.]+)%', line); return float(mm.group(1)) if mm else None
    if field == 'per_s':
        mm = re.search(r'([\d.]+)/s', line); return float(mm.group(1)) if mm else None
    mm = re.search(rf'{re.escape(field)}=([\d.]+)(µs|ms|s)?', line)
    if not mm:
        return None
    v = float(mm.group(1)); u = mm.group(2)
    return v / 1000 if u == 'µs' else v * 1000 if u == 's' else v


def f(v, nd=1):
    return '—' if v is None else f'{v:,.{nd}f}'.replace(',', ' ')


def d(a, b):
    return '—' if a in (None, 0) or b is None else f'{(b - a) / a * 100:+.0f} %'


out = []; P = out.append

# --- classic closed-model scenarios
P('### Classic scenarios (`linear`, `parallel`, `events`, `mixed` — the scripts\' own VU profiles)\n')
P('Closed model at the scripts\' default VU counts (500 / 500 / 200 / 40+30+30 VUs, 5 min with ramps) — far above this host\'s ceiling, so the admission limiter answers most starts with `429`; the scenario measures how much work each runtime gets through under that overload. Completed instances and process duration from the read model (`throughput.sql`), CPU = `docker stats` average over the k6 run.\n')
P('| scenario | runtime | completed | completed /s (peak 10 s) | process p50 / p99 (s) | requests /s | `429` / failed | start p95 (ms) | CPU Fleans / total (%) |')
P('|---|---|---:|---|---|---:|---:|---:|---|')
for sc in ['linear', 'parallel', 'events', 'mixed']:
    for lab in L:
        sqlt = rd(sc, lab, 'throughput.sql.txt'); k6 = rd(sc, lab, 'k6.txt')
        if not sqlt:
            continue
        rows = [r for r in sqlt.splitlines() if r.strip().startswith('load-')]
        cm = cpu_mem(sc, lab, 'load', 'drain')
        first = True
        for r in rows:
            c = [x.strip() for x in r.split('|')]
            label = f'`{sc}`' if first and lab == 'net10' else ''
            k6cells = (f"{f(k6metric(k6, 'http_reqs', 'per_s'), 0)} | {f(k6metric(k6, 'http_req_failed', 'rate%'), 1)} % | "
                       f"{f(k6metric(k6, 'workflow_start_duration', 'p(95)'), 0)} | {f(cm['fleans'], 0)} / {f(cm['total'], 0)}") if first else ' | | |'
            P(f"| {label} | {'.NET 10' if lab == 'net10' else '.NET 11'}{'' if len(rows) == 1 else ' ' + c[0]} | {c[1]} | {c[3]} ({c[4]}) | {c[5]} / {c[6]} | {k6cells} |")
            first = False
P('')

# --- timers
P('### `timers-1m` (10 000 timers armed at 100 starts/s, due within one minute)\n')
P('| runtime | armed | fired | failed / not fired | lag p50 / p99 / max (s) | starts answered `429` | CPU Fleans / total (%) |')
P('|---|---:|---:|---|---|---:|---|')
for SC, lab in [(a, b) for a in ('timers', 'timers2') for b in L]:
    t = rd(SC, lab, 'lag.sql.txt'); k6 = rd(SC, lab, 'k6.txt')
    m = re.search(r'^\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)', t, re.M)
    cm = cpu_mem(SC, lab)
    if m:
        P(f"| {'r2' if SC.endswith('2') else 'r1'} {lab} | {m.group(1)} | {m.group(2)} | {m.group(3)} / {m.group(4)} | {m.group(5)} / {m.group(6)} / {m.group(7)} | {f(k6metric(k6, 'http_req_failed', 'rate%'))} % | {f(cm['fleans'], 0)} / {f(cm['total'], 0)} |")
P('')

# --- signal fanout
P('### `signal-fanout` (10 000 parked at 100/s, one broadcast, linear-10 at 20/s before / during)\n')
P('| runtime | parked / received | broadcast answered | delivery spread | linear-10 started before → during | linear-10 duration p99 before → during |')
P('|---|---|---:|---:|---|---|')
for SC, lab in [(a, b) for a in ('signal', 'signal2') for b in L]:
    t = rd(SC, lab, 'signal.sql.txt'); k6 = rd(SC, lab, 'k6.txt')
    m = re.search(r'^\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|[^|]+\|[^|]+\|\s*([\d.]+)', t, re.M)
    b = re.search(r'^\s*before\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)', t, re.M)
    du = re.search(r'^\s*during\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)', t, re.M)
    a = re.search(r'answered in (\d+) ms', k6)
    if m and b and du:
        P(f"| {'r2' if SC.endswith('2') else 'r1'} {lab} | {m.group(1)} / {m.group(2)} | {a.group(1) if a else '—'} ms | {m.group(5)} s | {b.group(1)} → {du.group(1)} | {b.group(3)} s → {du.group(3)} s |")
P('')

# --- long-lived
P('### `long-lived` (10 000 instances parked on a message, linear-10 with 20 VUs before / after)\n')
P('| runtime | parked / still waiting | accepted linear-10 starts/s empty → loaded | drop | `429` empty / loaded | result |')
P('|---|---|---|---:|---|---|')
for SC, lab in [(a, b) for a in ('longlived', 'longlived2') for b in L]:
    t = rd(SC, lab, 'longlived.sql.txt'); k6 = rd(SC, lab, 'k6.txt')
    m = re.search(r'^\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|', t, re.M)
    s = re.search(r'starts/s empty ([\d.]+) → loaded ([\d.]+) \(drop (-?[\d.]+) %.*?: (PASS|FAIL); 429 empty (\d+) / loaded (\d+)', k6)
    if m and s:
        P(f"| {'r2' if SC.endswith('2') else 'r1'} {lab} | {m.group(1)} / {m.group(2)} | {s.group(1)} → {s.group(2)} | {s.group(3)} % | {s.group(5)} / {s.group(6)} | {s.group(4)} |")
P('')

# --- mi-fanout
P('### `mi-fanout` (one instance forks N branches, each waits for its own message)\n')
P('| branches | .NET 10: start answered / all delivered (r1, r2) | .NET 11: start answered / all delivered (r1, r2) | journal batches / events (both) |')
P('|---:|---|---|---|')
res = {}
for lab in L:
    for SC in ('mifanout', 'mifanout2'):
        for m in re.finditer(r'size=(\d+) id=\S+ start_ms=(\d+) delivered_s=([\d.]+)', rd(SC, lab, 'k6.txt')):
            res.setdefault((lab, int(m.group(1))), []).append((int(m.group(2)) / 1000, float(m.group(3))))
jr = [re.findall(r'\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*\d+\s*\|\s*\d+\s*$', rd('mifanout', lab, 'mi.sql.txt'), re.M) for lab in L]
for i, n in enumerate(sorted({k[1] for k in res})):
    a = res.get(('net10', n)); b = res.get(('net11', n))
    j = jr[0][i] if i < len(jr[0]) else ('—', '—')
    fm = lambda x: '—' if not x else ', '.join(f'{f(v[0], 1)} / {f(v[1], 1)} s' for v in x)
    P(f"| {n} | {fm(a)} | {fm(b)} | {j[0]} / {j[1]} |")
P('')

# --- soak
P('### Soak: `linear-10` at 45 starts/s, 5 min pre-warm + 30 s warm-up + **30 min** measured\n')
P('| runtime | started | completed | failed / unfinished | completed /s | p50 / p95 / p99 / max (s) | CPU total (%) | Fleans processes (%) | peak MiB core / worker / api |')
P('|---|---:|---:|---|---:|---|---:|---:|---|')
for lab in L:
    s = rd('soak', lab, 'tp/load-linear-10-summary.txt').splitlines()
    cpu = rd('soak', lab, 'tp/load-linear-10-45.cpu.txt')
    if len(s) < 2:
        continue
    c = [x.strip() for x in s[1].split(None, 1)[1].split('|')]
    tot = re.search(r'total\s+([\d.]+)', cpu)
    fl = sum(float(m.group(2)) for m in re.finditer(r'^(fleans-\S+|external-worker)\s+([\d.]+)', cpu, re.M))
    cm = cpu_mem('soak', lab)
    P(f"| {lab} | {c[0]} | {c[1]} | {c[2]} / {c[3]} | {c[4]} | {c[5]} / {c[6]} / {c[7]} / {c[8]} | {tot.group(1) if tot else '—'} | {f(fl, 0)} | {f(cm['peak_core'], 0)} / {f(cm['peak_worker'], 0)} / {f(cm['peak_api'], 0)} |")
P('')
P('### `fail` / `crit` log lines (Core / API / Worker / external worker)\n')
for sc in ['timers', 'timers2', 'signal', 'signal2', 'longlived', 'longlived2', 'mifanout', 'mifanout2', 'linear', 'parallel', 'events', 'mixed', 'soak']:
    cells = []
    for lab in L:
        t = rd(sc, lab, 'error-log-counts.txt')
        cells.append(f"{lab} " + ' / '.join(x.split()[1] for x in t.splitlines() if x.strip()) if t else f'{lab} —')
    P(f'- `{sc}`: ' + '; '.join(cells))
print('\n'.join(out))
