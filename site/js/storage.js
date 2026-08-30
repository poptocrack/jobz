// Suivi de candidatures en localStorage. Structure : { [jobId]: { s: statut, t: timestamp } }
const KEY = "jobz_suivi";

export const STATUTS = ["", "À postuler", "Candidaté", "Entretien", "Refusé", "Sans suite"];

function readAll() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

let cache = readAll();

export function getStatus(jobId) {
  return cache[jobId]?.s || "";
}

export function setStatus(jobId, statut) {
  if (statut) cache[jobId] = { s: statut, t: Date.now() };
  else delete cache[jobId];
  try {
    localStorage.setItem(KEY, JSON.stringify(cache));
  } catch { /* stockage indisponible : le suivi reste en mémoire */ }
}

export function trackedIds() {
  return new Set(Object.keys(cache));
}
