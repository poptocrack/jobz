// Worker : télécharge et décompresse les chunks .json.gz hors du thread UI.
self.onmessage = async (event) => {
  const { urls } = event.data;
  const jobs = [];
  for (const url of urls) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      let text;
      if (url.endsWith(".gz")) {
        const stream = resp.body.pipeThrough(new DecompressionStream("gzip"));
        text = await new Response(stream).text();
      } else {
        text = await resp.text();
      }
      const chunk = JSON.parse(text);
      jobs.push(...chunk);
      self.postMessage({ type: "progress", loaded: jobs.length });
    } catch (err) {
      self.postMessage({ type: "error", url, message: String(err) });
    }
  }
  self.postMessage({ type: "done", jobs });
};
