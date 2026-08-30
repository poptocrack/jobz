// Page Analyse : rendu des agrégats précalculés (data/analytics.json) avec Chart.js.
// Un seul ton (l'accent du site) pour les séries : chaque graphique compare des
// magnitudes, pas des identités. Grille en trait fin, tooltips, jumeau tableau.

import { phInit } from "./ph.js";
phInit();

const $ = (id) => document.getElementById(id);

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const THEME = {
  accent: css("--accent"),
  ink: css("--foreground"),
  muted: css("--muted-foreground"),
  grid: css("--border"),
};

Chart.defaults.font.family = '"Inter", -apple-system, sans-serif';
Chart.defaults.font.size = 11;
Chart.defaults.color = THEME.muted;

const fmtInt = (v) => Number(v).toLocaleString("fr-FR");
const fmtK = (v) => `${Math.round(v / 1000)} k€`;

async function fetchJson(name) {
  for (const base of ["data/", "../data/"]) {
    try {
      const resp = await fetch(new URL(base + name, location.href));
      if (resp.ok) return await resp.json();
    } catch { /* base suivante */ }
  }
  return null;
}

function baseOptions(overrides = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: css("--card"),
        titleColor: THEME.ink,
        bodyColor: THEME.muted,
        borderColor: THEME.grid,
        borderWidth: 1,
        padding: 10,
        displayColors: false,
      },
    },
    ...overrides,
  };
}

const hairline = { color: THEME.grid, lineWidth: 1 };

function hBar(canvasId, labels, values, { format = fmtInt, tooltip } = {}) {
  const wrap = $(canvasId).parentElement;
  wrap.style.height = `${Math.max(labels.length * 26 + 40, 120)}px`;
  new Chart($(canvasId), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: THEME.accent,
        borderRadius: { topRight: 4, bottomRight: 4 },
        borderSkipped: "left",
        barThickness: 14,
      }],
    },
    options: baseOptions({
      indexAxis: "y",
      layout: { padding: { right: 48 } },
      scales: {
        x: { grid: hairline, border: { display: false }, ticks: { callback: format } },
        y: { grid: { display: false }, border: { display: false }, ticks: { color: THEME.ink, autoSkip: false } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { ...baseOptions().plugins.tooltip, callbacks: tooltip ? { label: tooltip } : {} },
      },
      animation: { duration: 300 },
    }),
    plugins: [{
      // Étiquette de valeur en bout de barre (jumelle visible du tableau).
      afterDatasetsDraw(chart) {
        const { ctx } = chart;
        ctx.save();
        ctx.fillStyle = THEME.muted;
        ctx.font = '11px "Inter", sans-serif';
        ctx.textBaseline = "middle";
        chart.getDatasetMeta(0).data.forEach((bar, i) => {
          ctx.fillText(format(values[i]), bar.x + 6, bar.y);
        });
        ctx.restore();
      },
    }],
  });
}

function vBar(canvasId, labels, values, { format = fmtInt, tooltip } = {}) {
  new Chart($(canvasId), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: THEME.accent,
        borderRadius: { topLeft: 4, topRight: 4 },
        borderSkipped: "bottom",
        maxBarThickness: 34,
        categoryPercentage: 0.82,
      }],
    },
    options: baseOptions({
      scales: {
        x: { grid: { display: false }, border: { display: false } },
        y: { grid: hairline, border: { display: false }, ticks: { callback: format } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { ...baseOptions().plugins.tooltip, callbacks: tooltip ? { label: tooltip } : {} },
      },
      animation: { duration: 300 },
    }),
  });
}

function line(canvasId, labels, values, { format = fmtInt } = {}) {
  new Chart($(canvasId), {
    type: "line",
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: THEME.accent,
        backgroundColor: "transparent",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: THEME.accent,
        tension: 0.25,
      }],
    },
    options: baseOptions({
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, border: { display: false }, ticks: { maxTicksLimit: 8 } },
        y: { grid: hairline, border: { display: false }, ticks: { callback: format }, beginAtZero: true },
      },
      animation: { duration: 300 },
    }),
  });
}

function table(containerId, headers, rows) {
  $(containerId).innerHTML = `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function kpiTile(label, value, hint = "") {
  return `<div class="stat-tile"><div class="stat-value">${value}</div>
    <div class="stat-label">${label}</div>${hint ? `<div class="stat-hint">${hint}</div>` : ""}</div>`;
}

function bucketLabel(b) {
  if (b.de === null) return `< ${fmtInt(b.a)}`;
  if (b.a === null) return `≥ ${fmtInt(b.de)}`;
  return `${b.de / 1000}–${b.a / 1000}`;
}

async function init() {
  // Les largeurs d'axes dépendent de la police : attendre Inter avant de mesurer.
  try { await document.fonts.ready; } catch { /* mesure avec la police de repli */ }
  const [a, history] = await Promise.all([fetchJson("analytics.json"), fetchJson("history.json")]);
  if (!a) {
    $("kpi-row").innerHTML = `<div class="empty-state"><strong>Analyse indisponible.</strong><br>
      Les agrégats seront générés à la prochaine collecte.</div>`;
    $("meta-info").textContent = "";
    return;
  }

  const updated = new Date(a.generated_at);
  $("meta-info").textContent = `calculé le ${updated.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`;

  const k = a.kpis;
  $("kpi-row").innerHTML = [
    kpiTile("offres actives", fmtInt(k.total)),
    k.salaire_median_cdi ? kpiTile("salaire médian CDI", fmtK(k.salaire_median_cdi), "sur les offres avec salaire") : "",
    k.tjm_median ? kpiTile("TJM médian freelance", `${fmtInt(k.tjm_median)} €/j`) : "",
    kpiTile("offres avec salaire", `${k.pct_avec_salaire} %`),
    kpiTile("remote ou hybride", `${k.pct_teletravail} %`),
  ].filter(Boolean).join("");

  // Technos
  hBar("chart-technos", a.top_technos.map((t) => t.tag), a.top_technos.map((t) => t.n));
  table("table-technos", ["Techno", "Offres"], a.top_technos.map((t) => [t.tag, fmtInt(t.n)]));

  // Salaires par techno
  hBar("chart-salaires-techno",
    a.salaires_techno.map((t) => t.tag),
    a.salaires_techno.map((t) => t.mediane),
    { format: fmtK, tooltip: (ctx) => `${fmtK(ctx.raw)} · ${a.salaires_techno[ctx.dataIndex].n} offres` });
  table("table-salaires-techno", ["Techno", "Médiane", "Offres"],
    a.salaires_techno.map((t) => [t.tag, fmtK(t.mediane), fmtInt(t.n)]));

  // Distribution CDI
  vBar("chart-distribution",
    a.distribution_cdi.map(bucketLabel),
    a.distribution_cdi.map((b) => b.n),
    { tooltip: (ctx) => `${fmtInt(ctx.raw)} offres` });
  table("table-distribution", ["Tranche (k€)", "Offres"],
    a.distribution_cdi.map((b) => [bucketLabel(b), fmtInt(b.n)]));

  // Salaires par contrat
  const contrats = Object.entries(a.salaires_contrat);
  vBar("chart-contrats",
    contrats.map(([c]) => c),
    contrats.map(([, s]) => s.mediane),
    { format: fmtK, tooltip: (ctx) => {
        const s = contrats[ctx.dataIndex][1];
        return `médiane ${fmtK(s.mediane)} · Q1 ${fmtK(s.q1)} · Q3 ${fmtK(s.q3)} · ${fmtInt(s.n)} offres`;
      } });
  table("table-contrats", ["Contrat", "Médiane", "Q1", "Q3", "Offres"],
    contrats.map(([c, s]) => [c, fmtK(s.mediane), fmtK(s.q1), fmtK(s.q3), fmtInt(s.n)]));

  // TJM
  if (a.tjm) {
    $("note-tjm").textContent =
      `${fmtInt(a.tjm.n)} offres avec TJM · médiane ${fmtInt(a.tjm.mediane)} €/j · Q1 ${fmtInt(a.tjm.q1)} · Q3 ${fmtInt(a.tjm.q3)}`;
    vBar("chart-tjm",
      a.tjm.distribution.map((b) => (b.de === null ? `< ${b.a}` : b.a === null ? `≥ ${b.de}` : `${b.de}–${b.a}`)),
      a.tjm.distribution.map((b) => b.n),
      { tooltip: (ctx) => `${fmtInt(ctx.raw)} offres` });
    table("table-tjm", ["Tranche (€/j)", "Offres"],
      a.tjm.distribution.map((b) => [(b.de === null ? `< ${b.a}` : b.a === null ? `≥ ${b.de}` : `${b.de}–${b.a}`), fmtInt(b.n)]));
  } else {
    $("note-tjm").textContent = "Pas assez d'offres avec TJM affiché pour le moment.";
  }

  // Régions
  hBar("chart-regions", a.par_region.map((r) => r.region), a.par_region.map((r) => r.n));
  table("table-regions", ["Région", "Offres"], a.par_region.map((r) => [r.region, fmtInt(r.n)]));

  // Publications par jour
  line("chart-publications",
    a.publications_par_jour.map((p) => new Date(p.date + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short" })),
    a.publications_par_jour.map((p) => p.n));
  table("table-publications", ["Date", "Offres publiées"],
    a.publications_par_jour.map((p) => [p.date, fmtInt(p.n)]));

  // Transparence salariale
  const transp = Object.entries(a.transparence_salariale);
  vBar("chart-transparence",
    transp.map(([label]) => label),
    transp.map(([, v]) => v.pct),
    { format: (v) => `${v} %`, tooltip: (ctx) => `${ctx.raw} % de ${fmtInt(transp[ctx.dataIndex][1].n)} offres` });
  table("table-transparence", ["Employeur", "% avec salaire", "Offres"],
    transp.map(([label, v]) => [label, `${v.pct} %`, fmtInt(v.n)]));

  // Historique (visible dès 2 points)
  const points = history?.points || [];
  if (points.length >= 2) {
    $("card-history").hidden = false;
    line("chart-history",
      points.map((p) => new Date(p.date + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short" })),
      points.map((p) => p.total));
    table("table-history", ["Date", "Offres"], points.map((p) => [p.date, fmtInt(p.total)]));
  }

  // Top recruteurs
  const recruiterList = (items) =>
    `<ol>${items.map((r) => `<li><span>${r.entreprise}</span><span class="n">${fmtInt(r.n)}</span></li>`).join("")}</ol>`;
  $("list-clients-finaux").innerHTML = recruiterList(a.top_clients_finaux);
  $("list-esn").innerHTML = recruiterList(a.top_esn);
}

init();
