// Title autocomplete for every search box on the page.
document.querySelectorAll(".searchbox").forEach((form) => {
  const input = form.querySelector("input[name=q]");
  const list = form.querySelector(".suggestions");
  if (!input || !list) return;
  let timer = null, items = [], active = -1, ctrl = null;

  const close = () => { list.hidden = true; active = -1; };
  const render = () => {
    list.innerHTML = "";
    items.forEach((t, i) => {
      const li = document.createElement("li");
      li.textContent = t;
      li.setAttribute("role", "option");
      if (i === active) li.className = "active";
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        input.value = t;
        form.submit();
      });
      list.appendChild(li);
    });
    list.hidden = items.length === 0;
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { items = []; close(); return; }
    timer = setTimeout(async () => {
      try {
        if (ctrl) ctrl.abort();
        ctrl = new AbortController();
        const r = await fetch("/api/suggest?q=" + encodeURIComponent(q), { signal: ctrl.signal });
        items = await r.json();
        active = -1;
        render();
      } catch (_) { /* aborted or offline: ignore */ }
    }, 120);
  });

  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { active = (active + 1) % items.length; render(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = (active - 1 + items.length) % items.length; render(); e.preventDefault(); }
    else if (e.key === "Enter" && active >= 0) { input.value = items[active]; }
    else if (e.key === "Escape") { close(); }
  });
  input.addEventListener("blur", () => setTimeout(close, 100));
});
