DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>oxpipe</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a222c;
      --text: #e7ecf1;
      --muted: #8b9aab;
      --accent: #3d9cf0;
      --good: #3ecf8e;
      --warn: #e6a23c;
      --bad: #e35d6a;
      --border: #2a3542;
      --chip: #243040;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1a2a3a, var(--bg));
      color: var(--text);
      min-height: 100vh;
    }
    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border);
    }
    h1 { margin: 0; font-size: 1.25rem; letter-spacing: 0.02em; }
    h1 span { color: var(--accent); }
    .sub { color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }
    main { padding: 1.25rem 1.5rem 2rem; max-width: 1100px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }
    @media (max-width: 800px) { .grid { grid-template-columns: repeat(2, 1fr); } }
    .card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 10px; padding: 0.9rem 1rem;
    }
    .card .label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; }
    .card .value { font-size: 1.45rem; margin-top: 0.35rem; font-variant-numeric: tabular-nums; }
    .row { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1.25rem; }
    .panel { flex: 1 1 280px; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; }
    .panel h2 { margin: 0 0 0.75rem; font-size: 0.95rem; }
    .toggle {
      display: inline-flex; align-items: center; gap: 0.6rem; cursor: pointer; user-select: none;
    }
    .toggle input { display: none; }
    .track {
      width: 44px; height: 24px; border-radius: 999px; background: #3a4553; position: relative;
      transition: background .15s;
    }
    .track::after {
      content: ""; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px;
      border-radius: 50%; background: #fff; transition: transform .15s;
    }
    .toggle input:checked + .track { background: var(--good); }
    .toggle input:checked + .track::after { transform: translateX(20px); }
    .chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .chip {
      border: 1px solid var(--border); background: var(--chip); color: var(--text);
      border-radius: 999px; padding: 0.35rem 0.75rem; cursor: pointer; font-size: 0.85rem;
    }
    .chip.on { border-color: var(--accent); background: #1c3348; color: #9fd0ff; }
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th, td { text-align: left; padding: 0.45rem 0.35rem; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-weight: 500; }
    .ok { color: var(--good); }
    .no { color: var(--muted); }
    .mono { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.78rem; }
    .hint { color: var(--muted); font-size: 0.8rem; margin-top: 0.5rem; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>ox<span>pipe</span></h1>
      <div class="sub">GPT-5.5 / 5.6 context imaging · live counterfactual billing</div>
    </div>
    <div class="sub" id="updated">—</div>
  </header>
  <main>
    <div class="grid">
      <div class="card"><div class="label">Requests</div><div class="value" id="c-req">0</div></div>
      <div class="card"><div class="label">Imaged</div><div class="value" id="c-app">0</div></div>
      <div class="card"><div class="label">Baseline tokens</div><div class="value" id="c-base">0</div></div>
      <div class="card"><div class="label">Saved (eff)</div><div class="value" id="c-saved">0</div></div>
    </div>

    <div class="row">
      <div class="panel">
        <h2>Compression</h2>
        <label class="toggle">
          <input type="checkbox" id="kill" />
          <span class="track"></span>
          <span id="kill-label">off</span>
        </label>
        <div class="hint">Kill switch. When off, all requests passthrough even if models are allowlisted.</div>
      </div>
      <div class="panel">
        <h2>Model chips</h2>
        <div class="chips" id="chips"></div>
        <div class="hint">Prefix allowlist. Empty = imaging disabled. Env defaults apply until you toggle a chip.</div>
      </div>
    </div>

    <div class="panel" style="margin-top:1.25rem">
      <h2>Recent</h2>
      <table>
        <thead>
          <tr>
            <th>time</th><th>model</th><th>path</th><th>applied</th>
            <th>baseline</th><th>actual</th><th>saved</th><th>reason</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </main>
  <script>
    const fmt = (n) => {
      n = Number(n || 0);
      if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
      return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
    };
    let state = null;

    async function refresh() {
      const r = await fetch('/api/state');
      state = await r.json();
      document.getElementById('c-req').textContent = fmt(state.counters.requests);
      document.getElementById('c-app').textContent = fmt(state.counters.applied);
      document.getElementById('c-base').textContent = fmt(state.counters.baseline_tokens);
      document.getElementById('c-saved').textContent = fmt(state.counters.saved_eff);
      const kill = document.getElementById('kill');
      kill.checked = !!state.compression_enabled;
      document.getElementById('kill-label').textContent = kill.checked ? 'on' : 'off';
      const chips = document.getElementById('chips');
      chips.innerHTML = '';
      const active = new Set(state.models || []);
      (state.chips || []).forEach((id) => {
        const b = document.createElement('button');
        b.className = 'chip' + (active.has(id) || [...active].some(a => id.startsWith(a) || a.startsWith(id)) ? ' on' : '');
        // exact chip on if models includes this prefix or equal
        b.className = 'chip' + ([...active].some(a => a === id || id.startsWith(a)) ? ' on' : '');
        b.textContent = id;
        b.onclick = () => toggleChip(id);
        chips.appendChild(b);
      });
      const rows = document.getElementById('rows');
      rows.innerHTML = '';
      (state.recent || []).slice(0, 25).forEach((e) => {
        const tr = document.createElement('tr');
        const ts = (e.ts || '').replace('T', ' ').replace('Z','').slice(11, 19);
        tr.innerHTML = `
          <td class="mono">${ts}</td>
          <td class="mono">${e.model || ''}</td>
          <td class="mono">${e.path || ''}</td>
          <td class="${e.applied ? 'ok' : 'no'}">${e.applied ? 'yes' : 'no'}</td>
          <td class="mono">${fmt(e.baseline_tokens)}</td>
          <td class="mono">${fmt(e.input_tokens)}</td>
          <td class="mono">${fmt(e.saved_eff)}</td>
          <td class="mono">${e.reason || ''}</td>`;
        rows.appendChild(tr);
      });
      document.getElementById('updated').textContent = 'updated ' + new Date().toLocaleTimeString();
    }

    async function toggleChip(id) {
      const active = new Set(state.models || []);
      const on = [...active].some(a => a === id || id.startsWith(a));
      if (on) {
        // remove this chip and any that only existed via it
        const next = [...active].filter(a => a !== id && !a.startsWith(id));
        await fetch('/api/models', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ models: next }) });
      } else {
        const next = [...active, id];
        await fetch('/api/models', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ models: next }) });
      }
      await refresh();
    }

    document.getElementById('kill').addEventListener('change', async (ev) => {
      await fetch('/api/compression', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ enabled: ev.target.checked })
      });
      await refresh();
    });

    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""
