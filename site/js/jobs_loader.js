// Chargement des données : manifest + chunks gzip via le worker.
// Résout le dossier data en déploiement (./data/) comme en local (../data/).

const DATA_BASES = ["data/", "../data/"];

async function resolveBase() {
  for (const base of DATA_BASES) {
    try {
      // no-cache : revalidation systématique (304 si inchangé), pour que
      // chaque déploiement soit visible immédiatement.
      const resp = await fetch(new URL(base + "manifest.json", location.href), { cache: "no-cache" });
      if (resp.ok) return { base, manifest: await resp.json() };
    } catch { /* base suivante */ }
  }
  throw new Error("manifest.json introuvable");
}

export async function loadJobs(onProgress) {
  const { base, manifest } = await resolveBase();
  // Les chunks portent la version du build : jamais de données périmées en cache.
  const version = encodeURIComponent(manifest.generated_at || "");
  const urls = manifest.chunks.map(
    (c) => new URL(base + c.file + "?v=" + version, location.href).href
  );

  const jobs = await new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./chunk_worker.js", import.meta.url));
    worker.onmessage = (event) => {
      const msg = event.data;
      if (msg.type === "progress") onProgress?.(msg.loaded, manifest.total);
      else if (msg.type === "error") console.warn("Chunk en échec:", msg.url, msg.message);
      else if (msg.type === "done") { worker.terminate(); resolve(msg.jobs); }
    };
    worker.onerror = (err) => { worker.terminate(); reject(err); };
    worker.postMessage({ urls });
  });

  return { jobs, manifest };
}
