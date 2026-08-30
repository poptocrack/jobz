// Filtrage et tri côté client.
import { trackedIds } from "./storage.js";

export const defaultFilters = () => ({
  q: "",
  exclude: "",
  contrats: [],
  remote: "",
  employeur: "",
  region: "",
  source: "",
  salaireMin: 0, // en k€
  suiviesSeules: false,
  sort: "date",
});

const stripAccents = (s) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const ATS_SOURCES = new Set(["greenhouse", "lever", "ashby", "recruitee", "smartrecruiters", "workable"]);

// Regroupe les six ATS sous une seule valeur de filtre "ats".
export const sourceGroup = (source) => (ATS_SOURCES.has(source) ? "ats" : source);

// Index de recherche précalculé une fois par offre.
export function buildSearchIndex(jobs) {
  for (const job of jobs) {
    job._search = stripAccents(
      `${job.titre} ${job.entreprise} ${job.ville} ${job.tags.join(" ")}`
    );
  }
}

function parseTerms(input) {
  return stripAccents(input)
    .split(/[,;]+|\s{2,}/)
    .map((t) => t.trim())
    .filter(Boolean);
}

export function applyFilters(jobs, filters) {
  const qTerms = filters.q ? stripAccents(filters.q).split(/\s+/).filter(Boolean) : [];
  const excludeTerms = filters.exclude ? parseTerms(filters.exclude) : [];
  const tracked = filters.suiviesSeules ? trackedIds() : null;
  const salaireMin = filters.salaireMin * 1000;

  const result = jobs.filter((job) => {
    if (qTerms.length && !qTerms.every((t) => job._search.includes(t))) return false;
    if (excludeTerms.length && excludeTerms.some((t) => job._search.includes(t))) return false;
    if (filters.contrats.length && !filters.contrats.includes(job.contrat)) return false;
    if (filters.remote && job.teletravail !== filters.remote) return false;
    if (filters.employeur && (job.employeur_type || "inconnu") !== filters.employeur) return false;
    if (filters.region && job.region !== filters.region) return false;
    if (filters.source && sourceGroup(job.source) !== filters.source) return false;
    if (salaireMin && (job.salaire_max ?? job.salaire_min ?? 0) < salaireMin) return false;
    if (tracked && !tracked.has(job.id)) return false;
    return true;
  });

  sortJobs(result, filters.sort);
  return result;
}

function sortJobs(jobs, mode) {
  if (mode === "salaire") {
    jobs.sort((a, b) => (b.salaire_max ?? b.salaire_min ?? -1) - (a.salaire_max ?? a.salaire_min ?? -1));
  } else if (mode === "entreprise") {
    jobs.sort((a, b) => a.entreprise.localeCompare(b.entreprise, "fr") || (b.date_publication > a.date_publication ? 1 : -1));
  } else {
    jobs.sort((a, b) => (b.date_publication || "").localeCompare(a.date_publication || ""));
  }
}
