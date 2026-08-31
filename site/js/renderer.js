// Rendu des cartes d'offres.
import { STATUTS, getStatus, setStatus } from "./storage.js";

const SOURCE_LABELS = {
  france_travail: "France Travail",
  wttj: "Welcome to the Jungle",
  adzuna: "Adzuna",
  greenhouse: "Site carrière",
  lever: "Site carrière",
  ashby: "Site carrière",
  recruitee: "Site carrière",
  smartrecruiters: "Site carrière",
  workable: "Site carrière",
};

export const sourceLabel = (s) => SOURCE_LABELS[s] || s;

const escapeHtml = (s) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function formatSalary(job) {
  // Un TJM affiché prime sur l'annualisation pour les offres freelance/intérim.
  if (job.tjm_min || job.tjm_max) {
    const lo = job.tjm_min, hi = job.tjm_max;
    if (lo && hi && lo !== hi) return `${lo}–${hi} €/j`;
    return `${lo ?? hi} €/j`;
  }
  const fmt = (v) => Math.round(v / 1000);
  if (job.salaire_min && job.salaire_max && job.salaire_min !== job.salaire_max)
    return `${fmt(job.salaire_min)}–${fmt(job.salaire_max)} k€`;
  const v = job.salaire_min ?? job.salaire_max;
  return v ? `${fmt(v)} k€` : "";
}

const DAY_MS = 86400000;

function relativeDate(iso) {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso + "T12:00:00").getTime()) / DAY_MS);
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "hier";
  if (days < 30) return `il y a ${days} j`;
  return `il y a ${Math.floor(days / 30)} mois`;
}

export function isNew(job) {
  if (!job.date_publication) return false;
  return Date.now() - new Date(job.date_publication + "T12:00:00").getTime() < 2 * DAY_MS;
}

function ageDays(job) {
  if (!job.premiere_vue) return null;
  return Math.floor((Date.now() - new Date(job.premiere_vue + "T12:00:00").getTime()) / DAY_MS);
}

function jobCard(job) {
  const status = getStatus(job.id);
  const place = [job.ville, job.region && job.ville !== job.region ? job.region : ""]
    .filter(Boolean).join(", ");
  const salary = formatSalary(job);
  const age = ageDays(job);

  const badges = [
    isNew(job) ? `<span class="badge new">Nouvelle</span>` : "",
    job.employeur_type === "client final" ? `<span class="badge final">Client final</span>` : "",
    job.employeur_type === "esn" ? `<span class="badge esn">ESN / conseil</span>` : "",
    job.contrat ? `<span class="badge contrat">${escapeHtml(job.contrat)}</span>` : "",
    job.teletravail === "total" ? `<span class="badge">Full remote</span>` : "",
    job.teletravail === "hybride" ? `<span class="badge">Hybride</span>` : "",
    salary ? `<span class="badge salaire">${salary}</span>` : "",
    // Ancienneté RÉELLE (première observation par jobz), insensible aux reposts.
    age !== null && age > 30
      ? `<span class="badge age" title="Suivie par jobz depuis ${age} jours, malgré sa date de publication affichée">en ligne depuis ${age} j</span>`
      : "",
    ...job.tags.slice(0, 5).map((t) => `<span class="badge tag">${escapeHtml(t)}</span>`),
  ].filter(Boolean).join("");

  const options = STATUTS.map(
    (s) => `<option value="${s}"${s === status ? " selected" : ""}>${s || "Suivre…"}</option>`
  ).join("");

  return `
    <article class="job-card${status ? " tracked" : ""}" data-id="${job.id}">
      <div class="job-main">
        <a class="job-title" href="${escapeHtml(job.url)}" target="_blank" rel="noopener">${escapeHtml(job.titre)}</a>
        <div class="job-sub">
          <span class="company">${escapeHtml(job.entreprise)}</span>${place ? " · " + escapeHtml(place) : ""}
        </div>
        ${job.extrait ? `<p class="job-extrait">${escapeHtml(job.extrait)}</p>` : ""}
        <div class="badges">${badges}</div>
      </div>
      <div class="job-side">
        <span title="${escapeHtml(job.date_publication || "")} — via ${escapeHtml(sourceLabel(job.source))}">
          ${relativeDate(job.date_publication)} ·
          ${job.source === "adzuna"
            ? '<a href="https://www.adzuna.fr" rel="noopener" target="_blank" class="source-attrib">Jobs by Adzuna</a>'
            : escapeHtml(sourceLabel(job.source))}
        </span>
        <select class="track-select${status ? " has-status" : ""}" aria-label="Suivi de candidature">${options}</select>
      </div>
    </article>`;
}

export function renderJobs(container, jobs, onTrackChange) {
  if (!jobs.length) {
    container.innerHTML = `<div class="empty-state"><strong>Aucune offre ne correspond.</strong><br>Essayez d'élargir vos filtres.</div>`;
    return;
  }
  container.innerHTML = jobs.map(jobCard).join("");
  container.querySelectorAll(".track-select").forEach((select) => {
    select.addEventListener("change", (event) => {
      const card = event.target.closest(".job-card");
      setStatus(card.dataset.id, event.target.value);
      card.classList.toggle("tracked", Boolean(event.target.value));
      event.target.classList.toggle("has-status", Boolean(event.target.value));
      onTrackChange?.();
    });
  });
}

export function renderSkeletons(container, count = 6) {
  container.innerHTML = Array.from({ length: count }, () => `<div class="skeleton"></div>`).join("");
}
