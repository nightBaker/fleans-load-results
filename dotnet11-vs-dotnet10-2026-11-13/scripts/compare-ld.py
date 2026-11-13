#!/usr/bin/env python3
"""Isolated long-diverse rounds (ld*-net1x): k6 summary + CPU / memory from stats-timeline.txt."""
import json, os, re, statistics, collections, sys
RES = '/tmp/claude-0/work/results'
rounds = sorted({d.split('-')[0] for d in os.listdir(RES) if re.match(r'ld\d+-net1[01]$', d)})
LABELS = ['net10', 'net11']


def mib(s):
    m = re.match(r'([\d.]+)([KMG]i?B)', s)
    return float(m.group(1)) * {'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}.get(m.group(2), 1) if m else None


def stats(path):
    snaps = collections.defaultdict(lambda: collections.defaultdict(float))
    mem = collections.defaultdict(float)
    for l in open(path):
        p = l.split()
        if len(p) < 4 or not p[2].endswith('%'):
            continue
        try:
            cpu = float(p[2].rstrip('%'))
        except ValueError:
            continue
        svc = re.sub(r'^fleans-load-|-\d+$', '', p[1])
        snaps[p[0]][svc] += cpu
        snaps[p[0]]['total'] += cpu
        v = mib(p[3])
        if v:
            mem[svc] = max(mem[svc], v)
    keys = sorted(snaps)[2:-2]  # drop ramp edges
    cpu = {s: statistics.mean(snaps[k].get(s, 0) for k in keys) for s in {s for k in keys for s in snaps[k]}}
    return cpu, dict(mem)


rows = {}
for r in rounds:
    for lab in LABELS:
        d = f'{RES}/{r}-{lab}'
        if not os.path.exists(f'{d}/long-diverse.summary.json'):
            continue
        m = json.load(open(f'{d}/long-diverse.summary.json'))['metrics']
        g = lambda k, f: m.get(k, {}).get('values', {}).get(f)
        cpu, mem = stats(f'{d}/stats-timeline.txt')
        rows[(r, lab)] = dict(it=g('iterations', 'rate'), n=g('iterations', 'count'), ok=g('ld_completed', 'passes'),
                              okrate=g('ld_completed', 'rate'), httpf=g('http_req_failed', 'rate'),
                              e2e_med=g('ld_end_to_end', 'med'), e2e_p95=g('ld_end_to_end', 'p(95)'),
                              eng_med=g('ld_engine_duration', 'med'), eng_p95=g('ld_engine_duration', 'p(95)'),
                              st_med=g('workflow_start_duration', 'med'), st_p95=g('workflow_start_duration', 'p(95)'),
                              http_med=g('http_req_duration', 'med'), http_p95=g('http_req_duration', 'p(95)'),
                              msg_p95=g('message_accept_duration', 'p(95)'),
                              cpu=cpu.get('total'), core=cpu.get('fleans-core'), api=cpu.get('fleans-api'),
                              wrk=cpu.get('fleans-worker'), mem_core=mem.get('fleans-core'), mem_wrk=mem.get('fleans-worker'),
                              mem_api=mem.get('fleans-api'))
fields = [('it', 'completed iterations /s', 2), ('ok', 'instances completed (count)', 0), ('okrate', 'completed / started', 4),
          ('httpf', 'HTTP failed (rate)', 4), ('e2e_med', 'end-to-end med (ms)', 0), ('e2e_p95', 'end-to-end p95 (ms)', 0),
          ('eng_med', 'engine duration med (ms)', 0), ('eng_p95', 'engine duration p95 (ms)', 0),
          ('st_med', 'start request med (ms)', 1), ('st_p95', 'start request p95 (ms)', 1),
          ('http_med', 'all HTTP med (ms)', 1), ('http_p95', 'all HTTP p95 (ms)', 1), ('msg_p95', 'message accept p95 (ms)', 1),
          ('cpu', 'CPU, whole stack (% of one core)', 0), ('core', 'CPU, fleans-core ×3', 0), ('api', 'CPU, fleans-api ×2', 0),
          ('wrk', 'CPU, fleans-worker', 0), ('mem_core', 'peak MiB, fleans-core', 0), ('mem_api', 'peak MiB, fleans-api', 0),
          ('mem_wrk', 'peak MiB, fleans-worker', 0)]
hdr = ' | '.join(f'{r} {l}' for r in rounds for l in LABELS)
print(f'| metric | {hdr} | mean .NET 10 | mean .NET 11 | Δ |')
print('|---|' + '---:|' * (len(rounds) * 2 + 3))
f = lambda v, nd: '—' if v is None else f'{v:.{nd}f}'
for k, name, nd in fields:
    cells = [f(rows.get((r, l), {}).get(k), nd) for r in rounds for l in LABELS]
    a = [rows[(r, 'net10')][k] for r in rounds if (r, 'net10') in rows and rows[(r, 'net10')][k] is not None]
    b = [rows[(r, 'net11')][k] for r in rounds if (r, 'net11') in rows and rows[(r, 'net11')][k] is not None]
    ma, mb = (statistics.mean(a) if a else None), (statistics.mean(b) if b else None)
    d = '—' if not ma or mb is None else f'{(mb - ma) / ma * 100:+.1f} %'
    print(f'| {name} | ' + ' | '.join(cells) + f' | {f(ma, nd)} | {f(mb, nd)} | {d} |')
