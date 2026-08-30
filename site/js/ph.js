// Analytics PostHog (EU) : pageviews + événements produit essentiels.
// Config sobre : pas d'autocapture, pas de session recording, profils uniquement
// anonymes, persistance localStorage (pas de cookie tiers).

const PH_KEY = "phc_nRGNe7A8NJHcav24khrcxbEnpRQA5EpXRVAxUeMUeYZU";
const PH_HOST = "https://eu.i.posthog.com";

let ready = false;
const queue = [];

export function phInit() {
  if (window.posthog || ready) return;
  const script = document.createElement("script");
  script.src = `${PH_HOST.replace("eu.i", "eu-assets.i")}/static/array.js`;
  script.onload = () => {
    window.posthog.init(PH_KEY, {
      api_host: PH_HOST,
      autocapture: false,
      capture_pageview: true,
      capture_pageleave: true,
      disable_session_recording: true,
      person_profiles: "identified_only",
      persistence: "localStorage",
    });
    ready = true;
    for (const [event, props] of queue) window.posthog.capture(event, props);
    queue.length = 0;
  };
  document.head.appendChild(script);
}

export function phCapture(event, props = {}) {
  if (ready && window.posthog) window.posthog.capture(event, props);
  else queue.push([event, props]);
}
