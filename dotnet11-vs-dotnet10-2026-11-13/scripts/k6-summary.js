// Minimal stand-in for jslib k6-summary textSummary (jslib.k6.io is unreachable here).
export function textSummary(data, opts) {
  const lines = [];
  for (const name of Object.keys(data.metrics).sort()) {
    const m = data.metrics[name];
    const v = Object.entries(m.values).map(([k, x]) => `${k}=${typeof x === 'number' ? Math.round(x * 1000) / 1000 : x}`).join(' ');
    lines.push(`  ${name.padEnd(40, '.')}: ${v}`);
  }
  return lines.join('\n') + '\n';
}
