// Synchronisation des filtres avec l'URL (recherches partageables).
import { defaultFilters } from "./filters.js";

const PARAM_MAP = {
  q: "q",
  exclude: "excl",
  remote: "tt",
  employeur: "emp",
  region: "region",
  source: "src",
  sort: "tri",
};

export function filtersToUrl(filters, view) {
  const params = new URLSearchParams();
  for (const [key, param] of Object.entries(PARAM_MAP)) {
    if (filters[key] && filters[key] !== defaultFilters()[key]) params.set(param, filters[key]);
  }
  if (filters.contrats.length) params.set("contrat", filters.contrats.join(","));
  if (filters.salaireMin) params.set("salmin", String(filters.salaireMin));
  if (filters.suiviesSeules) params.set("suivies", "1");
  if (view === "map") params.set("vue", "carte");
  const qs = params.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

export function filtersFromUrl() {
  const params = new URLSearchParams(location.search);
  const filters = defaultFilters();
  for (const [key, param] of Object.entries(PARAM_MAP)) {
    if (params.has(param)) filters[key] = params.get(param);
  }
  if (params.has("contrat")) filters.contrats = params.get("contrat").split(",").filter(Boolean);
  if (params.has("salmin")) filters.salaireMin = Number(params.get("salmin")) || 0;
  filters.suiviesSeules = params.get("suivies") === "1";
  const view = params.get("vue") === "carte" ? "map" : "list";
  return { filters, view };
}
