// Page Sources : volume et fraîcheur par source, depuis le manifest.
import { phInit } from "./ph.js";
phInit();

document.getElementById("theme-toggle")?.addEventListener("click", () => {
  const root = document.documentElement;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = root.dataset.theme === "dark" || (!root.dataset.theme && systemDark);
  root.dataset.theme = isDark ? "light" : "dark";
  try { localStorage.setItem("jobz_theme", root.dataset.theme); } catch { /* mémoire session */ }
});

const ATS = ["greenhouse", "lever", "ashby", "recruitee", "smartrecruiters", "workable"];

const META = {
  france_travail: {
    nom: "France Travail",
    type: "API officielle",
    cadence: "toutes les heures",
    description: "L'API publique Offres d'emploi v2, filtrée sur les métiers du numérique.",
  },
  wttj: {
    nom: "Welcome to the Jungle",
    type: "Index public du site",
    cadence: "toutes les heures",
    description: "Les catégories tech et produit, France uniquement.",
  },
  adzuna: {
    nom: "Adzuna",
    type: "API officielle",
    cadence: "toutes les heures",
    description: "La catégorie IT du marché France (offres de sites privés).",
  },
  ats: {
    nom: "Sites carrière des entreprises",
    type: "APIs publiques des ATS",
    cadence: "3 fois par jour",
    description: "1 400+ entreprises recrutant en France via Greenhouse, Lever, Ashby, Recruitee, SmartRecruiters et Workable, filtrées sur les postes tech.",
  },
};

const ATS_LABELS = {
  greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby",
  recruitee: "Recruitee", smartrecruiters: "SmartRecruiters", workable: "Workable",
};

function relative(iso) {
  if (!iso) return "—";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours} h${minutes % 60 ? ` ${String(minutes % 60).padStart(2, "0")}` : ""}`;
  return `il y a ${Math.floor(hours / 24)} j`;
}

function freshnessClass(iso, cadence) {
  if (!iso) return "stale";
  const hours = (Date.now() - new Date(iso).getTime()) / 3600000;
  const limit = cadence === "toutes les heures" ? 2.5 : 9;
  return hours <= limit ? "fresh" : "stale";
}

async function init() {
  let manifest = null;
  for (const base of ["data/", "../data/"]) {
    try {
      const resp = await fetch(new URL(base + "manifest.json", location.href), { cache: "no-cache" });
      if (resp.ok) { manifest = await resp.json(); break; }
    } catch { /* base suivante */ }
  }
  const container = document.getElementById("sources-list");
  if (!manifest) {
    container.innerHTML = `<div class="empty-state">Impossible de charger les données.</div>`;
    return;
  }

  const updated = new Date(manifest.generated_at);
  document.getElementById("meta-info").textContent =
    `${manifest.total.toLocaleString("fr-FR")} offres · publication ${relative(manifest.generated_at)}`;

  const sources = manifest.sources || {};
  const cards = [];

  for (const key of ["france_travail", "wttj", "adzuna"]) {
    const s = sources[key] || {};
    cards.push(card(META[key], s.offres || 0, s.dernier_fetch, null));
  }

  // Les six ATS agrégés en une carte, avec le détail par plateforme.
  const atsEntries = ATS.map((k) => [k, sources[k]]).filter(([, v]) => v && v.offres);
  const atsTotal = atsEntries.reduce((sum, [, v]) => sum + v.offres, 0);
  const atsFetch = atsEntries.map(([, v]) => v.dernier_fetch).filter(Boolean).sort().pop();
  const detail = atsEntries
    .map(([k, v]) => `<span>${ATS_LABELS[k]} <strong>${v.offres.toLocaleString("fr-FR")}</strong></span>`)
    .join("");
  cards.push(card(META.ats, atsTotal, atsFetch, detail));

  container.innerHTML = cards.join("");
}

function card(meta, offres, dernierFetch, detail) {
  return `
  <article class="source-card">
    <div class="source-head">
      <h2>${meta.nom}</h2>
      <span class="badge">${meta.type}</span>
    </div>
    <p class="source-desc">${meta.description}</p>
    <div class="source-stats">
      <div><span class="stat-value">${offres.toLocaleString("fr-FR")}</span><span class="stat-label">offres publiées</span></div>
      <div>
        <span class="stat-value freshness ${freshnessClass(dernierFetch, meta.cadence)}">${relative(dernierFetch)}</span>
        <span class="stat-label">dernier passage · ${meta.cadence}</span>
      </div>
    </div>
    ${detail ? `<div class="source-detail">${detail}</div>` : ""}
  </article>`;
}

init();
