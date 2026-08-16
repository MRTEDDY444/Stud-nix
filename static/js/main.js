(function () {
  "use strict";

  // ---- Dark / light mode ----
  const root = document.documentElement;
  const themeToggle = document.getElementById("theme-toggle");
  const stored = localStorage.getItem("sh-theme");
  if (stored) root.setAttribute("data-theme", stored);
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
    root.setAttribute("data-theme", "dark");
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      const current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
      const next = current === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      localStorage.setItem("sh-theme", next);
    });
  }

  // ---- Mobile nav ----
  const navToggle = document.getElementById("nav-toggle");
  const mainNav = document.getElementById("main-nav");
  if (navToggle && mainNav) {
    navToggle.addEventListener("click", function () {
      const isOpen = mainNav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", String(isOpen));
    });
  }

  // ---- AI Study Helper buttons (search results page) ----
  const helperBtns = document.querySelectorAll(".helper-btn");
  const helperOutput = document.getElementById("helper-output");
  const topic = window.STUDENT_HUB_TOPIC || "";
  const helperContext = window.STUDENT_HUB_CONTEXT || "";

  helperBtns.forEach(function (btn) {
    btn.addEventListener("click", async function () {
      const action = btn.getAttribute("data-action");
      if (!helperOutput) return;
      helperOutput.hidden = false;
      helperOutput.textContent = "Working on it…";
      try {
        const resp = await fetch("/api/ai-helper", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: action, topic: topic, context: helperContext }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(function () { return {}; });
          helperOutput.textContent = data.error || "AI Study Helper is temporarily unavailable. You can still browse the available resources.";
          return;
        }
        const data = await resp.json();
        const result = data.result;
        if (Array.isArray(result)) {
          helperOutput.textContent = result
            .map(function (item, i) {
              if (typeof item === "object") return (i + 1) + ". " + (item.front ? item.front + " — " + item.back : JSON.stringify(item));
              return (i + 1) + ". " + item;
            })
            .join("\n");
        } else {
          helperOutput.textContent = result || "No response.";
        }
      } catch (e) {
        helperOutput.textContent = "We couldn't reach the AI Study Helper. Please try again.";
      }
    });
  });
})();
