(() => {
  "use strict";

  const body = document.body;
  const announcer = document.querySelector("#portal-announcer");

  const announce = (message) => {
    if (!announcer) return;
    announcer.textContent = "";
    window.setTimeout(() => {
      announcer.textContent = message;
    }, 30);
  };

  const navPanel = document.querySelector("[data-nav-panel]");
  const navToggle = document.querySelector("[data-nav-toggle]");
  const navClosers = document.querySelectorAll("[data-nav-close]");
  const mobileNavigation = window.matchMedia("(max-width: 960px)");

  if (navPanel && navToggle) {
    let restoreFocus = false;

    const setNavigationState = (open, moveFocus = true) => {
      const mobile = mobileNavigation.matches;
      const shouldOpen = mobile && open;

      body.classList.toggle("nav-open", shouldOpen);
      navToggle.setAttribute("aria-expanded", String(shouldOpen));
      navToggle.setAttribute("aria-label", shouldOpen ? "Fechar menu" : "Abrir menu");

      if (mobile) {
        navPanel.toggleAttribute("inert", !shouldOpen);
        navPanel.setAttribute("aria-hidden", String(!shouldOpen));
      } else {
        navPanel.removeAttribute("inert");
        navPanel.removeAttribute("aria-hidden");
      }

      if (shouldOpen) {
        restoreFocus = true;
        if (moveFocus) {
          navPanel.querySelector("[data-nav-close]")?.focus();
        }
      } else if (restoreFocus && moveFocus) {
        restoreFocus = false;
        navToggle.focus();
      }
    };

    navToggle.addEventListener("click", () => {
      setNavigationState(!body.classList.contains("nav-open"));
    });

    navClosers.forEach((closer) => {
      closer.addEventListener("click", () => setNavigationState(false));
    });

    navPanel.querySelectorAll('a[href^="#"]').forEach((link) => {
      link.addEventListener("click", () => {
        if (mobileNavigation.matches) setNavigationState(false, false);
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && body.classList.contains("nav-open")) {
        setNavigationState(false);
      }
    });

    mobileNavigation.addEventListener("change", () => setNavigationState(false, false));
    setNavigationState(false, false);
  }

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const inputId = button.getAttribute("data-password-toggle");
    const input = inputId ? document.getElementById(inputId) : null;
    if (!input) return;

    button.addEventListener("click", () => {
      const revealing = input.type === "password";
      input.type = revealing ? "text" : "password";
      button.textContent = revealing ? "Ocultar" : "Mostrar";
      button.setAttribute("aria-pressed", String(revealing));
      button.setAttribute("aria-label", revealing ? "Ocultar senha" : "Mostrar senha");
      input.focus({ preventScroll: true });
    });
  });

  document.querySelectorAll("form[data-submit-once]").forEach((form) => {
    form.addEventListener("submit", () => {
      const submitButton = form.querySelector('button[type="submit"]');
      if (!submitButton) return;

      submitButton.disabled = true;
      submitButton.setAttribute("aria-busy", "true");
      const label = submitButton.querySelector("span") || submitButton;
      label.textContent = submitButton.getAttribute("data-submit-label") || "Processando…";
    });
  });

  const normalize = (value) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR")
      .trim();

  document.querySelectorAll("[data-table-search]").forEach((search) => {
    const tableId = search.getAttribute("data-table-search");
    const table = tableId ? document.getElementById(tableId) : null;
    const panel = search.closest(".table-panel");
    if (!table || !panel) return;

    const rows = Array.from(table.querySelectorAll("[data-search-row]"));
    const count = panel.querySelector("[data-result-count]");
    const empty = panel.querySelector("[data-empty-filter]");

    const filterRows = () => {
      const query = normalize(search.value);
      let visible = 0;

      rows.forEach((row) => {
        const matches = !query || normalize(row.textContent || "").includes(query);
        row.hidden = !matches;
        if (matches) visible += 1;
      });

      if (count) count.textContent = `${visible} ${visible === 1 ? "item" : "itens"}`;
      if (empty) empty.hidden = visible !== 0;
      table.closest(".table-scroll")?.toggleAttribute("hidden", visible === 0);
      announce(`${visible} ${visible === 1 ? "relatório encontrado" : "relatórios encontrados"}`);
    };

    search.addEventListener("input", filterRows);
  });

  const mapRoot = document.querySelector(".feature-map");
  if (mapRoot) {
    const cards = Array.from(mapRoot.querySelectorAll("[data-map-card]"));
    const search = mapRoot.querySelector("[data-map-search]");
    const chips = Array.from(mapRoot.querySelectorAll("[data-map-filter='theme']"));
    let theme = "all";

    const applyMapFilter = () => {
      const query = normalize(search ? search.value : "");
      let visible = 0;
      cards.forEach((card) => {
        const cardTheme = card.getAttribute("data-theme") || "engine";
        const matchesTheme = theme === "all" || cardTheme === theme;
        const matchesQuery = !query || normalize(card.textContent || "").includes(query);
        const show = matchesTheme && matchesQuery;
        card.hidden = !show;
        if (show) visible += 1;
      });
      announce(`${visible} ${visible === 1 ? "feature visível" : "features visíveis"}`);
    };

    chips.forEach((chip) => {
      chip.addEventListener("click", () => {
        theme = chip.getAttribute("data-map-value") || "all";
        chips.forEach((item) => item.classList.toggle("is-active", item === chip));
        applyMapFilter();
      });
    });
    search?.addEventListener("input", applyMapFilter);
  }

  const finePointer = window.matchMedia("(pointer: fine)").matches;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (finePointer && !reducedMotion) {
    document.querySelectorAll("[data-tilt-card]").forEach((card) => {
      let frame = 0;

      card.addEventListener("pointermove", (event) => {
        window.cancelAnimationFrame(frame);
        frame = window.requestAnimationFrame(() => {
          const bounds = card.getBoundingClientRect();
          const horizontal = (event.clientX - bounds.left) / bounds.width - 0.5;
          const vertical = (event.clientY - bounds.top) / bounds.height - 0.5;
          card.style.setProperty("--rotate-x", `${vertical * -3.5}deg`);
          card.style.setProperty("--rotate-y", `${horizontal * 4.5}deg`);
        });
      });

      card.addEventListener("pointerleave", () => {
        window.cancelAnimationFrame(frame);
        card.style.setProperty("--rotate-x", "0deg");
        card.style.setProperty("--rotate-y", "0deg");
      });
    });
  }

  const liveRoot = document.querySelector("[data-snapshot-activity]");
  let renderedActivity = liveRoot?.getAttribute("data-snapshot-activity") || "";

  if (liveRoot && renderedActivity) {
    window.setInterval(async () => {
      if (document.hidden) return;
      try {
        const response = await window.fetch("/api/heartbeat", {
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const state = await response.json();
        const nextActivity = String(state.last_activity || "");
        if (nextActivity && nextActivity !== renderedActivity) {
          renderedActivity = nextActivity;
          window.location.reload();
        }
      } catch (_error) {
        // A temporary snapshot/service interruption must not break the dashboard.
      }
    }, 30_000);
  }
})();
