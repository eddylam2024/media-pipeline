const POLL_MS = 15000;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 4000);
}

async function getJSON(path) {
  const r = await fetch(path);
  return r.json();
}

async function postJSON(action, params) {
  const r = await fetch(`/api/action/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  const body = await r.json();
  if (!r.ok) {
    toast(`${action} failed: ${body.error || body.stderr || JSON.stringify(body)}`);
  } else {
    toast(`${action} ok`);
  }
  return { ok: r.ok, body };
}

// ---------------------------------------------------------------- sections

async function renderGateway() {
  const jobs = await getJSON("/api/jobs");
  const pill = document.getElementById("gateway-pill");
  const running = !!jobs.gateway_running;
  pill.textContent = running ? "gateway: running" : "gateway: STOPPED";
  pill.className = "pill " + (running ? "ok" : "bad");
  return jobs;
}

function renderFunnel(data) {
  const c = data.status_counts;
  const days = data.trailing_7d.map((d) => {
    const zero = d.honest_zero ? ' <span class="badge bad">honest zero</span>' : "";
    return `<div class="row"><span>${esc(d.date)}</span>
      <span>scouted ${d.scouted} · produced ${d.produced}${zero}</span></div>`;
  }).join("");
  document.getElementById("funnel-body").innerHTML = `
    <div class="row"><span>collected</span><span class="badge">${c.collected}</span></div>
    <div class="row"><span>scouted</span><span class="badge">${c.scouted}</span></div>
    <div class="row"><span>produced</span><span class="badge">${c.produced}</span></div>
    <div class="row"><span>published (all time)</span><span class="badge ok">${data.published_total}</span></div>
    ${days}`;
}

function jobRow(j) {
  const stale = j.stale ? '<span class="badge stale">stale</span>' : "";
  const status = j.last_status === "ok" ? '<span class="badge ok">ok</span>'
    : j.last_status ? `<span class="badge bad">${esc(j.last_status)}</span>` : "";
  return `<div class="item">
    <div class="item-title">${esc(j.name)} <span class="hint">${esc(j.id)}</span></div>
    <div class="item-meta">schedule ${esc(j.schedule)} · last run ${esc(j.last_run || "never")} ${status} ${stale}</div>
    <div class="actions">
      <button data-act="run_now" data-job="${esc(j.id)}">Run now</button>
      <button data-act="pause" data-job="${esc(j.id)}">Pause</button>
      <button data-act="resume" data-job="${esc(j.id)}">Resume</button>
    </div>
  </div>`;
}

function parseCronList(raw) {
  // parses `hermes cron list` box output into structured rows
  const jobs = [];
  const blocks = raw.split(/\n\n(?=\s{2}[0-9a-f]{12})/);
  for (const b of blocks) {
    const id = (b.match(/^\s*([0-9a-f]{12})/m) || [])[1];
    if (!id) continue;
    const name = (b.match(/Name:\s*(.+)/) || [])[1];
    const schedule = (b.match(/Schedule:\s*(.+)/) || [])[1];
    const lastRunMatch = b.match(/Last run:\s*(\S+)\s+(\w+)/);
    jobs.push({
      id, name: name || id, schedule: schedule || "?",
      last_run: lastRunMatch ? lastRunMatch[1] : null,
      last_status: lastRunMatch ? lastRunMatch[2] : null,
    });
  }
  return jobs;
}

function renderJobs(jobsRaw) {
  const jobs = parseCronList(jobsRaw.cron_list_raw || "");
  document.getElementById("jobs-body").innerHTML =
    jobs.length ? jobs.map(jobRow).join("") : `<div class="empty">no jobs found</div>`;
}

function renderQC(data) {
  if (!data.reels || !data.reels.length) {
    document.getElementById("qc-body").innerHTML =
      `<div class="empty">no produced reels for ${esc(data.date || "any day")}</div>`;
    return;
  }
  document.getElementById("qc-body").innerHTML = data.reels.map((r) => {
    if (r.qc_missing) {
      return `<div class="item">
        <div class="item-title">${esc(r.topic || r.folder)}</div>
        <div class="qc-missing">⚠ no qc_frames recorded — QC gate should have blocked this</div>
      </div>`;
    }
    const dur = (r.source?.end ?? 0) - (r.source?.start ?? 0);
    const dots = r.qc_frames.map((f) => {
      const pct = dur > 0 ? Math.round(((f.t - r.source.start) / dur) * 100) : 0;
      return `<span class="qc-dot ${f.verdict === "fail" ? "fail" : ""}"
        title="t=${esc(f.t)}s: ${esc(f.description)} (${esc(f.verdict)})"></span>`;
    }).join("");
    return `<div class="item">
      <div class="item-title">${esc(r.topic || r.folder)}</div>
      <div class="item-meta">${esc(r.hook || "")}</div>
      <div class="item-meta">source: ${esc(r.source?.title || "?")} — ${esc(r.source?.channel || "?")}</div>
      <div class="qc-strip">${dots}</div>
    </div>`;
  }).join("");
}

function queueItem(item) {
  const clip = item.has_render
    ? `<video controls preload="none" src="/media/queue/${encodeURIComponent(item.name)}/reel.mp4"></video>`
    : item.has_clip
    ? `<video controls preload="none" src="/media/queue/${encodeURIComponent(item.name)}/clip_01.mp4"></video>`
    : `<div class="empty">no rendered clip yet</div>`;
  return `<div class="item" data-name="${esc(item.name)}">
    <div class="item-title">${esc(item.hook || item.name)}</div>
    <div class="item-meta">${esc(item.caption || "")}</div>
    ${clip}
    <textarea class="hook-edit" placeholder="edit hook…">${esc(item.hook || "")}</textarea>
    <div class="actions">
      <button data-act="edit" data-name="${esc(item.name)}">Save + re-render</button>
      <button data-act="skip" data-name="${esc(item.name)}">Skip</button>
      <button class="primary" data-act="publish" data-name="${esc(item.name)}">Approve &amp; publish</button>
    </div>
  </div>`;
}

function renderQueue(data) {
  document.getElementById("queue-body").innerHTML =
    data.queue.length ? data.queue.map(queueItem).join("")
    : `<div class="empty">queue is empty</div>`;
}

function renderPosted(data) {
  document.getElementById("posted-body").innerHTML =
    data.posted.length ? data.posted.map((p) => `<div class="item">
      <div class="item-title">${esc(p.id)}</div>
      <div class="item-meta">ig_media_id ${esc(p.ig_media_id)} · posted ${esc(p.posted_at || "?")}</div>
      <div class="item-meta">${esc(p.caption || "")}</div>
      ${p.performance ? `<div class="item-meta">views ${esc(p.performance.views ?? "?")} · likes ${esc(p.performance.likes ?? "?")}</div>` : ""}
    </div>`).join("") : `<div class="empty">nothing published yet</div>`;
}

function renderSkipped(data) {
  document.getElementById("skipped-body").innerHTML =
    data.skipped.length ? data.skipped.map((s) => `<div class="row">
      <span>${esc(s.name)}</span><span class="badge">${esc(s.bucket)}</span>
    </div>`).join("") : `<div class="empty">nothing skipped</div>`;
}

function renderSources(data) {
  document.getElementById("sources-body").innerHTML =
    data.channels.length ? data.channels.map((c) => `<div class="row">
      <span>${esc(c.channel)}</span><span class="badge">${c.count}</span>
    </div>`).join("") : `<div class="empty">no source data yet</div>`;
}

// ---------------------------------------------------------------- actions

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const act = btn.dataset.act;
  const name = btn.dataset.name;
  const job = btn.dataset.job;

  if (act === "publish") {
    const typed = prompt(`Type "publish" to confirm posting "${name}" to Instagram:`);
    if (typed !== "publish") { toast("publish cancelled"); return; }
    await postJSON("publish", { name, confirm: "publish" });
  } else if (act === "skip") {
    if (!confirm(`Move "${name}" to skipped/?`)) return;
    await postJSON("skip", { name });
  } else if (act === "edit") {
    const item = btn.closest(".item");
    const hook = item.querySelector(".hook-edit").value;
    await postJSON("edit", { name, hook });
  } else if (act === "pause" || act === "resume") {
    if (!confirm(`${act} job ${job}?`)) return;
    await postJSON(act, { job_id: job });
  } else if (act === "run_now") {
    if (!confirm(`Run job ${job} now?`)) return;
    await postJSON("run_now", { job_id: job });
  } else if (act === "gateway_restart") {
    if (!confirm("Restart the media-pipeline gateway service?")) return;
    await postJSON("gateway_restart", {});
  }
  refreshAll();
});

// ---------------------------------------------------------------- polling

async function refreshAll() {
  try {
    const [jobsRaw, funnel, qc, queue, posted, skipped, sources] = await Promise.all([
      renderGateway(),
      getJSON("/api/funnel"),
      getJSON("/api/qc"),
      getJSON("/api/queue"),
      getJSON("/api/posted"),
      getJSON("/api/skipped"),
      getJSON("/api/sources"),
    ]);
    renderJobs(jobsRaw);
    renderFunnel(funnel);
    renderQC(qc);
    renderQueue(queue);
    renderPosted(posted);
    renderSkipped(skipped);
    renderSources(sources);
  } catch (e) {
    toast("refresh failed: " + e);
  }
}

refreshAll();
setInterval(refreshAll, POLL_MS);
