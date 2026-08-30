// Vue carte : Leaflet + clustering, chargés paresseusement au premier affichage.
import { sourceLabel } from "./renderer.js";

let leafletReady = null;
let map = null;
let clusterGroup = null;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Échec de chargement : ${src}`));
    document.head.appendChild(script);
  });
}

async function ensureLeaflet() {
  if (!leafletReady) {
    leafletReady = (async () => {
      await loadScript("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
      await loadScript("https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js");
    })();
  }
  return leafletReady;
}

const escapeHtml = (s) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export async function showMap(jobs) {
  await ensureLeaflet();

  if (!map) {
    map = L.map("map", { preferCanvas: true }).setView([46.6, 2.4], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    clusterGroup = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 46 });
    map.addLayer(clusterGroup);
  }

  // La carte a pu être initialisée pendant que son conteneur était masqué.
  setTimeout(() => map.invalidateSize(), 60);

  clusterGroup.clearLayers();
  const markers = [];
  for (const job of jobs) {
    if (job.lat == null || job.lon == null) continue;
    const marker = L.marker([job.lat, job.lon]);
    marker.bindPopup(
      `<div class="map-popup">
        <a href="${escapeHtml(job.url)}" target="_blank" rel="noopener">${escapeHtml(job.titre)}</a><br>
        ${escapeHtml(job.entreprise)} · ${escapeHtml(job.ville || "")}
        <div class="popup-more">${escapeHtml(job.contrat || "")} · via ${escapeHtml(sourceLabel(job.source))}</div>
      </div>`
    );
    markers.push(marker);
  }
  clusterGroup.addLayers(markers);
  return markers.length;
}
