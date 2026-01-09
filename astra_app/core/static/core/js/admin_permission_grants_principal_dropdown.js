(function () {
  "use strict";

  function buildPrincipalsUrl() {
    // We want the *model admin root* URL, not a URL relative to the current
    // page. On change pages, using ../principals/ incorrectly yields:
    //   /admin/.../<id>/principals/
    // but our endpoint is:
    //   /admin/.../principals/
    const path = String(window.location.pathname || "");
    // Handle both:
    // - .../add/ (or .../add)
    // - .../<object_id>/change/ (or .../<object_id>/change)
    // Note: Django uses <path:object_id> so it may not be numeric.
    const basePath = path.replace(/(?:[^/]+\/change\/?|add\/?)$/, "");
    return new URL(`${basePath}principals/`, window.location.origin);
  }

  async function refreshPrincipalNames() {
    const principalTypeSelect = document.getElementById("id_principal_type");
    const principalNameSelect = document.getElementById("id_principal_name");

    if (!principalTypeSelect || !principalNameSelect) {
      return;
    }

    const selectedType = String(principalTypeSelect.value || "").trim();
    const previousValue = String(principalNameSelect.value || "").trim();

    const url = buildPrincipalsUrl();
    url.searchParams.set("principal_type", selectedType);

    let data;
    try {
      const resp = await fetch(url.toString(), {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
        credentials: "same-origin",
      });

      if (!resp.ok) {
        // eslint-disable-next-line no-console
        console.warn("Permission Grants: failed to fetch principals", resp.status, url.toString());
        return;
      }

      data = await resp.json();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("Permission Grants: unable to load principals", e, url.toString());
      return;
    }

    const principals = Array.isArray(data?.principals) ? data.principals : [];

    // Rebuild options.
    principalNameSelect.innerHTML = "";

    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "---------";
    principalNameSelect.appendChild(blank);

    for (const item of principals) {
      const id = typeof item === "string" ? item : String(item?.id || "");
      const text = typeof item === "string" ? item : String(item?.text || item?.id || "");
      if (!id) {
        continue;
      }

      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = text;
      principalNameSelect.appendChild(opt);
    }

    // Preserve selection if possible.
    if (previousValue) {
      principalNameSelect.value = previousValue;
      if (principalNameSelect.value !== previousValue) {
        principalNameSelect.value = "";
      }
    }

    // Keep any dependent logic in sync.
    try {
      principalNameSelect.dispatchEvent(new Event("change", { bubbles: true }));
    } catch (_e) {
      // Ignore.
    }
  }

  function init() {
    const principalTypeSelect = document.getElementById("id_principal_type");
    if (!principalTypeSelect) {
      return;
    }

    function currentPrincipalTypeValue() {
      const el = document.getElementById("id_principal_type");
      return el ? String(el.value || "").trim() : "";
    }

    function refreshFromEvent() {
      void refreshPrincipalNames();
    }

    principalTypeSelect.addEventListener("change", refreshFromEvent);

    // Some environments/widgets can be picky about when 'change' fires; also
    // listen for 'input'.
    principalTypeSelect.addEventListener("input", refreshFromEvent);

    // Defensive: if admin JS swaps the element out, this delegated listener
    // still catches the event.
    document.addEventListener(
      "change",
      function (e) {
        const target = e.target;
        if (target && target.id === "id_principal_type") {
          refreshFromEvent();
        }
      },
      true,
    );

    // Fallback: in some environments the principal_type UI changes value but
    // doesn't consistently emit native DOM events. Polling a single field is
    // cheap and keeps the dropdown reliable.
    let lastValue = currentPrincipalTypeValue();
    window.setInterval(function () {
      const now = currentPrincipalTypeValue();
      if (now && now !== lastValue) {
        lastValue = now;
        void refreshPrincipalNames();
      }
    }, 500);

    // Ensure the dropdown is always in-sync on page load.
    void refreshPrincipalNames();

  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
