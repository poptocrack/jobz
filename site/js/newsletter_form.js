// Inscription aux alertes email : POST vers le formulaire Brevo (double opt-in),
// avec les critères de recherche courants embarqués en attributs de contact.

const FORM_ACTION =
  "https://87e3a7b1.sibforms.com/serve/MUIFANKKtUooqKnZ1tylcGRqn9nHtPDOgNbRBz8yzgYNc8FI5lrEXidRAwP9t8-jexK16Bffrtwp-PSjqUUO6ukfeXZ-g8FXuCMCpKaZDgmDORJ-r9tomDwdOV31ltrZg7IXqpylb0Xya_UocYYqypasMgcnInCrKw7Y8igezi9jH1SsxFSs5qDjcYClJsQS-ka9bU_95qH6OBtk?isAjax=1";

const $ = (id) => document.getElementById(id);

function currentCriteria() {
  return {
    Q: $("search-input")?.value.trim() || "",
    CONTRATS: [...document.querySelectorAll("#contract-chips .chip.active")]
      .map((chip) => chip.dataset.value).join(","),
    REMOTE: $("remote-select")?.value || "",
    REGION: $("region-select")?.value || "",
    EMPLOYEUR: $("employer-select")?.value || "",
    SALAIRE_MIN: $("salary-input")?.value || "",
  };
}

function criteriaSummary(criteria) {
  const parts = [
    criteria.Q && `« ${criteria.Q} »`,
    criteria.CONTRATS,
    criteria.REMOTE,
    criteria.REGION,
    criteria.EMPLOYEUR === "client final" ? "client final" : criteria.EMPLOYEUR === "esn" ? "ESN" : "",
    criteria.SALAIRE_MIN && `≥ ${criteria.SALAIRE_MIN} k€`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "toutes les offres";
}

export function initNewsletterForm() {
  const form = $("alert-form");
  if (!form) return;
  const status = $("alert-status");
  const summary = $("alert-summary");

  const refreshSummary = () => {
    summary.textContent = `Critères actuels : ${criteriaSummary(currentCriteria())}`;
  };
  refreshSummary();
  document.querySelector(".layout").addEventListener("input", refreshSummary);
  document.querySelector(".layout").addEventListener("click", () => setTimeout(refreshSummary, 50));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = $("alert-email").value.trim();
    if (!email) return;

    const body = new FormData();
    body.set("EMAIL", email);
    body.set("email_address_check", "");
    body.set("locale", "fr");
    body.set("html_type", "simple");
    // Critères sérialisés dans l'attribut CRITERES (seul champ déclaré côté Brevo).
    const criteria = currentCriteria();
    const serialized = Object.entries(criteria)
      .filter(([, value]) => value)
      .map(([key, value]) => `${key}=${value}`)
      .join("|");
    body.set("CRITERES", serialized);

    status.textContent = "Inscription…";
    status.className = "alert-status";
    try {
      const resp = await fetch(FORM_ACTION, { method: "POST", body });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.success !== false) {
        status.textContent = "Presque fini ! Ouvrez l'email de confirmation qui vient de partir.";
        status.classList.add("ok");
        form.querySelector("button").disabled = true;
        import("./ph.js").then(({ phCapture }) => phCapture("newsletter_inscription", {
          avec_recherche: Boolean(currentCriteria().Q),
        })).catch(() => {});
      } else {
        throw new Error(data.message || "réponse invalide");
      }
    } catch {
      status.textContent = "Impossible de vous inscrire pour le moment, réessayez plus tard.";
      status.classList.add("err");
    }
  });
}
