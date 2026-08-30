// Pagination fenêtrée avec ellipses.
export const PAGE_SIZE = 50;

export function paginate(jobs, page) {
  const pages = Math.max(1, Math.ceil(jobs.length / PAGE_SIZE));
  const current = Math.min(Math.max(1, page), pages);
  return {
    pages,
    current,
    slice: jobs.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE),
  };
}

export function renderPagination(nav, pages, current, onPage) {
  if (pages <= 1) {
    nav.innerHTML = "";
    return;
  }
  const items = [];
  const add = (p) => items.push(p);
  add("prev");
  const window = 2;
  let last = 0;
  for (let p = 1; p <= pages; p++) {
    if (p === 1 || p === pages || Math.abs(p - current) <= window) {
      if (last && p - last > 1) add("…");
      add(p);
      last = p;
    }
  }
  add("next");

  nav.innerHTML = items
    .map((item) => {
      if (item === "prev")
        return `<button data-page="${current - 1}" ${current === 1 ? "disabled" : ""} aria-label="Page précédente">‹</button>`;
      if (item === "next")
        return `<button data-page="${current + 1}" ${current === pages ? "disabled" : ""} aria-label="Page suivante">›</button>`;
      if (item === "…") return `<span class="ellipsis">…</span>`;
      return `<button data-page="${item}" class="${item === current ? "current" : ""}">${item}</button>`;
    })
    .join("");

  nav.querySelectorAll("button[data-page]").forEach((btn) =>
    btn.addEventListener("click", () => {
      onPage(Number(btn.dataset.page));
      document.querySelector(".search-bar").scrollIntoView({ behavior: "smooth" });
    })
  );
}
