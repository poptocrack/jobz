// Orchestrateur : chargement, état, câblage des contrôles, rendu.
import { loadJobs } from "./jobs_loader.js";
import { applyFilters, buildSearchIndex, defaultFilters, sourceGroup } from "./filters.js";
import { renderJobs, renderSkeletons, sourceLabel } from "./renderer.js";
import { PAGE_SIZE, paginate, renderPagination } from "./pagination.js";
import { filtersFromUrl, filtersToUrl } from "./url_state.js";
import { showMap } from "./map_view.js";
import { initNewsletterForm } from "./newsletter_form.js";
import { phCapture, phInit } from "./ph.js";

const $ = (id) => document.getElementById(id);

const state = {
  jobs: [],
  filtered: [],
  filters: defaultFilters(),
  page: 1,
  view: "list",
};

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function populateSelect(select, counts, labelFn = (v) => v) {
  const entries = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  for (const [value, count] of entries) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = `${labelFn(value)} (${count.toLocaleString("fr-FR")})`;
    select.appendChild(option);
  }
}

function countBy(jobs, key) {
  const counts = new Map();
  for (const job of jobs) {
    const value = job[key];
    if (value) counts.set(value, (counts.get(value) || 0) + 1);
  }
  return counts;
}

// Nombre de filtres actifs dans le panneau latéral (la recherche vit à part).
function activeFilterCount() {
  const f = state.filters;
  return (
    (f.exclude ? 1 : 0) + f.contrats.length + (f.remote ? 1 : 0) +
    (f.employeur ? 1 : 0) + (f.region ? 1 : 0) + (f.source ? 1 : 0) +
    (f.salaireMin ? 1 : 0) + (f.suiviesSeules ? 1 : 0)
  );
}

function hasActiveFilters() {
  return activeFilterCount() > 0 || state.filters.q !== "";
}

function render({ resetPage = true } = {}) {
  if (resetPage) state.page = 1;
  state.filtered = applyFilters(state.jobs, state.filters);
  filtersToUrl(state.filters, state.view);
  $("reset-filters").hidden = !hasActiveFilters();
  const filterCount = activeFilterCount();
  $("filter-count").hidden = filterCount === 0;
  $("filter-count").textContent = String(filterCount);

  const total = state.filtered.length;
  const countText = total
    ? `<strong>${total.toLocaleString("fr-FR")}</strong> offre${total > 1 ? "s" : ""}`
    : "Aucune offre";
  $("result-count").innerHTML = state.view === "map"
    ? `${countText} · les offres sans localisation précise ne sont pas affichées sur la carte`
    : countText;

  if (state.view === "map") {
    showMap(state.filtered).catch((err) => {
      console.error(err);
      $("result-count").textContent = "Impossible de charger la carte.";
    });
  } else {
    const { pages, current, slice } = paginate(state.filtered, state.page);
    state.page = current;
    renderJobs($("jobs-container"), slice, () => {
      if (state.filters.suiviesSeules) render({ resetPage: false });
    });
    renderPagination($("pagination"), pages, current, (page) => {
      state.page = page;
      render({ resetPage: false });
    });
  }
}

function setView(view) {
  state.view = view;
  $("view-list").classList.toggle("active", view === "list");
  $("view-map").classList.toggle("active", view === "map");
  $("view-list").setAttribute("aria-selected", String(view === "list"));
  $("view-map").setAttribute("aria-selected", String(view === "map"));
  $("list-view").hidden = view !== "list";
  $("map-view").hidden = view !== "map";
  render({ resetPage: false });
}

function syncControls() {
  const f = state.filters;
  $("search-input").value = f.q;
  $("exclude-input").value = f.exclude;
  $("remote-select").value = f.remote;
  $("employer-select").value = f.employeur;
  $("region-select").value = f.region;
  $("source-select").value = f.source;
  $("salary-input").value = f.salaireMin || "";
  $("tracked-only").checked = f.suiviesSeules;
  $("sort-select").value = f.sort;
  document.querySelectorAll("#contract-chips .chip").forEach((chip) =>
    chip.classList.toggle("active", f.contrats.includes(chip.dataset.value))
  );
}

function wireControls() {
  $("search-input").addEventListener("input", debounce((e) => {
    state.filters.q = e.target.value.trim();
    render();
  }, 180));

  // Événements produit : recherche stabilisée, clic sur offre, bascule carte.
  $("search-input").addEventListener("change", (e) => {
    if (e.target.value.trim()) phCapture("recherche", { q: e.target.value.trim(), resultats: state.filtered.length });
  });
  $("jobs-container").addEventListener("click", (e) => {
    const link = e.target.closest(".job-title");
    if (!link) return;
    const card = link.closest(".job-card");
    const job = state.filtered.find((j) => j.id === card?.dataset.id);
    if (job) phCapture("offre_cliquee", { source: job.source, employeur_type: job.employeur_type || "inconnu", contrat: job.contrat });
  });

  $("exclude-input").addEventListener("input", debounce((e) => {
    state.filters.exclude = e.target.value.trim();
    render();
  }, 250));

  document.querySelectorAll("#contract-chips .chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      const value = chip.dataset.value;
      const list = state.filters.contrats;
      const index = list.indexOf(value);
      if (index >= 0) list.splice(index, 1);
      else list.push(value);
      chip.classList.toggle("active", index < 0);
      render();
    })
  );

  const bindSelect = (id, key) =>
    $(id).addEventListener("change", (e) => {
      state.filters[key] = e.target.value;
      render();
    });
  bindSelect("remote-select", "remote");
  bindSelect("employer-select", "employeur");
  bindSelect("region-select", "region");
  bindSelect("source-select", "source");
  bindSelect("sort-select", "sort");

  $("salary-input").addEventListener("input", debounce((e) => {
    state.filters.salaireMin = Number(e.target.value) || 0;
    render();
  }, 300));

  $("tracked-only").addEventListener("change", (e) => {
    state.filters.suiviesSeules = e.target.checked;
    render();
  });

  $("reset-filters").addEventListener("click", () => {
    state.filters = defaultFilters();
    syncControls();
    render();
  });

  $("view-list").addEventListener("click", () => setView("list"));
  $("view-map").addEventListener("click", () => { setView("map"); phCapture("vue_carte"); });

  $("filters-toggle").addEventListener("click", () => {
    const panel = document.querySelector(".panel");
    const open = panel.classList.toggle("open");
    $("filters-toggle").setAttribute("aria-expanded", String(open));
  });

  $("theme-toggle")?.addEventListener("click", () => {
    const root = document.documentElement;
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = root.dataset.theme === "dark" || (!root.dataset.theme && systemDark);
    root.dataset.theme = isDark ? "light" : "dark";
    try { localStorage.setItem("jobz_theme", root.dataset.theme); } catch { /* mémoire session */ }
  });
}

async function init() {
  phInit();
  renderSkeletons($("jobs-container"));
  const fromUrl = filtersFromUrl();
  state.filters = fromUrl.filters;
  state.view = fromUrl.view;

  try {
    const { jobs, manifest } = await loadJobs((loaded, total) => {
      $("meta-info").textContent = `Chargement… ${loaded.toLocaleString("fr-FR")}/${total.toLocaleString("fr-FR")}`;
    });
    state.jobs = jobs;
    buildSearchIndex(jobs);

    const updated = new Date(manifest.generated_at);
    $("meta-info").textContent =
      `${manifest.total.toLocaleString("fr-FR")} offres · mis à jour le ${updated.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`;

    populateSelect($("region-select"), countBy(jobs, "region"));

    const sourceCounts = new Map();
    for (const job of jobs) {
      const group = sourceGroup(job.source);
      sourceCounts.set(group, (sourceCounts.get(group) || 0) + 1);
    }
    const sourceGroupLabels = {
      ats: "Sites carrière (direct)",
      wttj: "Welcome to the Jungle",
      france_travail: "France Travail",
      adzuna: "Adzuna",
    };
    populateSelect($("source-select"), sourceCounts, (v) => sourceGroupLabels[v] || v);

    wireControls();
    syncControls();
    initNewsletterForm();

    // Liens segments SEO dans le footer (générés au build).
    fetch(new URL("data/seo_links.json", location.href)).catch(() => null).then(async (resp) => {
      if (!resp?.ok) return;
      const links = await resp.json();
      $("seo-links").innerHTML = links
        .map((l) => `<a href="${l.url}">${l.label}</a>`).join("");
    }).catch(() => {});
    if (state.view === "map") setView("map");
    else render({ resetPage: false });
  } catch (err) {
    console.error(err);
    $("jobs-container").innerHTML =
      `<div class="empty-state"><strong>Impossible de charger les offres.</strong><br>Réessayez dans quelques instants.</div>`;
    $("meta-info").textContent = "Erreur de chargement";
  }
}

init();
