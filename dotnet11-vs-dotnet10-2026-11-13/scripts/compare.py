#!/usr/bin/env python3
"""Summarise /tmp/claude-0/work/results/<round>-<label>/ into markdown comparison tables."""
import json, os, re, sys, glob, statistics, collections

RES = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/work/results'
LABELS = ['net10', 'net11']
rounds = sorted({d.split('-')[0] for d in os.listdir(RES) if re.match(r'r\d+-net1[01]$', d)})


def ladder(dirpath, process):
    rows = {}
    f = os.path.join(dirpath, f'{process}-summary.txt')
    if not os.path.exists(f):
        return rows
    for line in open(f).read().splitlines()[1:]:
        rate, rest = line.split(None, 1)
        parts = [p.strip() for p in rest.split('|')]
        if len(parts) < 9:
            continue
        started, completed, failed, nf, cps, p50, p95, p99, mx = parts
        cpu = None
        cf = os.path.join(dirpath, f'{process}-{rate}.cpu.txt')
        per_svc = {}
        if os.path.exists(cf):
            for l in open(cf):
                m = re.match(r'(\S+)\s+([\d.]+) %', l)
                if m:
                    per_svc[m.group(1)] = float(m.group(2))
            cpu = per_svc.get('total')
        k6f = os.path.join(dirpath, f'{process}-{rate}.k6.txt')
        dropped = failed_http = None
        if os.path.exists(k6f):
            t = open(k6f).read()
            m = re.search(r'dropped_iterations\.*: (\d+)', t); dropped = int(m.group(1)) if m else 0
            m = re.search(r'http_req_failed\.*: ([\d.]+)%', t); failed_http = float(m.group(1)) if m else None
        f2 = lambda x: float(x) if x not in ('', None) else None
        rows[int(rate)] = dict(started=int(started or 0), completed=int(completed or 0), failed=int(failed or 0),
                               not_finished=int(nf or 0), cps=f2(cps), p50=f2(p50), p95=f2(p95), p99=f2(p99),
                               max=f2(mx), cpu=cpu, svc=per_svc, dropped=dropped, http_failed=failed_http)
    return rows


def mem_parse(s):
    m = re.match(r'([\d.]+)([KMG]i?B)', s)
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2)
    return v * {'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024, 'kB': 1 / 1000, 'MB': 1, 'GB': 1000, 'B': 1 / 1048576}.get(u, 1)


def svc_of(name):
    return re.sub(r'^fleans-load-|-\d+$', '', name)


def mem_snapshot(path):
    """service -> average MiB per container (snapshot file: name cpu mem / limit)."""
    per = collections.defaultdict(list)
    if not os.path.exists(path):
        return {}
    for l in open(path):
        p = l.split()
        if len(p) >= 3:
            v = mem_parse(p[2])
            if v is not None:
                per[svc_of(p[0])].append(v)
    return {k: statistics.mean(v) for k, v in per.items()}


def mem_peak(path):
    """service -> peak MiB of any single container over the round."""
    peak = collections.defaultdict(float)
    if not os.path.exists(path):
        return {}
    for l in open(path):
        p = l.split()
        if len(p) >= 3:
            v = mem_parse(p[2])
            if v is not None:
                s = svc_of(p[1]); peak[s] = max(peak[s], v)
    return dict(peak)


def long_diverse(path):
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))['metrics']
    g = lambda m, k: d.get(m, {}).get('values', {}).get(k)
    return dict(iter_rate=g('iterations', 'rate'), iters=g('iterations', 'count'),
                completed=g('ld_completed', 'rate'), failed=g('ld_instance_failed', 'rate'),
                e2e_med=g('ld_end_to_end', 'med'), e2e_p95=g('ld_end_to_end', 'p(95)'),
                eng_med=g('ld_engine_duration', 'med'), eng_p95=g('ld_engine_duration', 'p(95)'),
                start_med=g('workflow_start_duration', 'med'), start_p95=g('workflow_start_duration', 'p(95)'),
                http_p95=g('http_req_duration', 'p(95)'), http_med=g('http_req_duration', 'med'),
                http_failed=g('http_req_failed', 'rate'), checks=g('checks', 'rate'),
                msg_p95=g('message_accept_duration', 'p(95)'))


data = {}
for r in rounds:
    for lab in LABELS:
        d = os.path.join(RES, f'{r}-{lab}')
        if not os.path.isdir(d):
            continue
        st = open(os.path.join(d, 'startup.txt')).read().split()[-1] if os.path.exists(os.path.join(d, 'startup.txt')) else None
        data[(r, lab)] = dict(
            startup=float(st) if st else None,
            lin=ladder(os.path.join(d, 'linear10'), 'load-linear-10'),
            one=ladder(os.path.join(d, 'onetask'), 'load-one-task'),
            ld=long_diverse(os.path.join(d, 'long-diverse.summary.json')),
            idle=mem_snapshot(os.path.join(d, 'idle-stats.txt')),
            after=mem_snapshot(os.path.join(d, 'after-stats.txt')),
            peak=mem_peak(os.path.join(d, 'mem-timeline.txt')),
            errors=open(os.path.join(d, 'error-log-counts.txt')).read().split('\n') if os.path.exists(os.path.join(d, 'error-log-counts.txt')) else [],
        )


def mean(vals):
    vals = [v for v in vals if v is not None]
    return statistics.mean(vals) if vals else None


def fmt(v, nd=3, unit=''):
    return '—' if v is None else f'{v:.{nd}f}{unit}'


def delta(a, b, lower_better=True):
    if a in (None, 0) or b is None:
        return '—'
    pct = (b - a) / a * 100
    return f'{pct:+.1f} %'


out = []
P = out.append
P(f'Rounds: {", ".join(rounds)} (each round = fresh stack, net10 then net11)\n')

for key, title, proc in [('lin', '`linear-10` (10 script tasks, no waits)', 'load-linear-10'),
                         ('one', '`one-task` (one external `e2e-probe` task on gRPC workers, 50 ms)', 'load-one-task')]:
    P(f'### {title}\n')
    P('Mean of the rounds. Latency = process duration from the read model (`CompletedAt − CreatedAt`), seconds; CPU = sum over all containers, % of one core.\n')
    P('| offered /s | .NET 10 done/s | .NET 11 done/s | .NET 10 p50 / p95 / p99 | .NET 11 p50 / p95 / p99 | Δ p99 | .NET 10 CPU | .NET 11 CPU | Δ CPU |')
    P('|---:|---:|---:|---|---|---:|---:|---:|---:|')
    rates = sorted({rt for (r, lab), v in data.items() for rt in v[key]})
    for rt in rates:
        agg = {}
        for lab in LABELS:
            rows = [data[(r, lab)][key].get(rt) for r in rounds if (r, lab) in data]
            rows = [x for x in rows if x]
            agg[lab] = {f: mean([x[f] for x in rows]) for f in ('cps', 'p50', 'p95', 'p99', 'cpu')} if rows else {}
        a, b = agg.get('net10', {}), agg.get('net11', {})
        P(f"| {rt} | {fmt(a.get('cps'),1)} | {fmt(b.get('cps'),1)} | {fmt(a.get('p50'))} / {fmt(a.get('p95'))} / {fmt(a.get('p99'))} | "
          f"{fmt(b.get('p50'))} / {fmt(b.get('p95'))} / {fmt(b.get('p99'))} | {delta(a.get('p99'), b.get('p99'))} | "
          f"{fmt(a.get('cpu'),0)} | {fmt(b.get('cpu'),0)} | {delta(a.get('cpu'), b.get('cpu'))} |")
    P('')
    P('Per round (p50 / p99 s, CPU %):\n')
    P('| offered /s | ' + ' | '.join(f'{r} {lab}' for r in rounds for lab in LABELS) + ' |')
    P('|---:|' + '---|' * (len(rounds) * len(LABELS)))
    for rt in rates:
        cells = []
        for r in rounds:
            for lab in LABELS:
                x = data.get((r, lab), {}).get(key, {}).get(rt)
                cells.append('—' if not x else f"{fmt(x['p50'])} / {fmt(x['p99'])}, {fmt(x['cpu'],0)}" + (f", {x['failed']} failed" if x['failed'] else '') + (f", {x['not_finished']} unfinished" if x['not_finished'] else ''))
        P(f'| {rt} | ' + ' | '.join(cells) + ' |')
    P('')
    # per-service CPU at a mid rate
    P('CPU per service (% of one core, mean of rounds):\n')
    for rt in rates:
        svcs = sorted({s for (r, lab), v in data.items() if v[key].get(rt) for s in v[key][rt]['svc']} - {'total'})
        if not svcs:
            continue
        line = []
        for s in svcs:
            if not re.match(r'fleans-|external-worker', s):
                continue
            a = mean([data[(r, 'net10')][key][rt]['svc'].get(s) for r in rounds if (r, 'net10') in data and data[(r, 'net10')][key].get(rt)])
            b = mean([data[(r, 'net11')][key][rt]['svc'].get(s) for r in rounds if (r, 'net11') in data and data[(r, 'net11')][key].get(rt)])
            line.append(f'{s} {fmt(a,0)} → {fmt(b,0)}')
        P(f'- {rt}/s: ' + '; '.join(line))
    P('')

P('### `long-diverse` (≈45 nodes, 4 client interactions + external task), constant VUs\n')
P('| metric | .NET 10 | .NET 11 | Δ |')
P('|---|---:|---:|---:|')
for f, name, nd in [('iter_rate', 'completed iterations /s', 2), ('e2e_med', 'end-to-end med (ms)', 0), ('e2e_p95', 'end-to-end p95 (ms)', 0),
                    ('eng_med', 'engine duration med (ms)', 0), ('eng_p95', 'engine duration p95 (ms)', 0),
                    ('start_med', 'start request med (ms)', 1), ('start_p95', 'start request p95 (ms)', 1),
                    ('http_med', 'all HTTP med (ms)', 1), ('http_p95', 'all HTTP p95 (ms)', 1), ('msg_p95', 'message accept p95 (ms)', 1),
                    ('completed', 'instances completed (rate)', 3), ('failed', 'instances failed (rate)', 3), ('checks', 'checks passed (rate)', 4),
                    ('http_failed', 'HTTP failed (rate)', 4)]:
    a = mean([data[(r, 'net10')]['ld'].get(f) for r in rounds if (r, 'net10') in data])
    b = mean([data[(r, 'net11')]['ld'].get(f) for r in rounds if (r, 'net11') in data])
    P(f'| {name} | {fmt(a, nd)} | {fmt(b, nd)} | {delta(a, b)} |')
P('')

P('### Memory (MiB per container, mean of rounds)\n')
P('| service | idle .NET 10 | idle .NET 11 | peak .NET 10 | peak .NET 11 | after load .NET 10 | after load .NET 11 |')
P('|---|---:|---:|---:|---:|---:|---:|')
for s in ['fleans-core', 'fleans-api', 'fleans-worker', 'external-worker']:
    vals = []
    for f in ('idle', 'peak', 'after'):
        for lab in LABELS:
            vals.append(mean([data[(r, lab)][f].get(s) for r in rounds if (r, lab) in data]))
    P(f'| {s} | ' + ' | '.join(fmt(v, 0) for v in vals) + ' |')
P('')
P('### Startup (`docker compose up -d --wait`, whole stack, s)\n')
P('| | ' + ' | '.join(rounds) + ' |')
P('|---|' + '---:|' * len(rounds))
for lab in LABELS:
    P(f'| {lab} | ' + ' | '.join(fmt(data.get((r, lab), {}).get('startup'), 1) for r in rounds) + ' |')
P('')
P('### `fail`/`crit` log lines per service over the round\n')
for (r, lab), v in sorted(data.items()):
    P(f'- {r} {lab}: ' + ', '.join(x for x in v['errors'] if x))
print('\n'.join(out))
