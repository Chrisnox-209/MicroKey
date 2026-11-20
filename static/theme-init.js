// Restore only the visual preference, before the first paint. No credentials are stored.
(() => {
  let theme = "dark";
  try { if (localStorage.getItem("microkey-theme-spotlight") === "light") theme = "light"; } catch (_) {}
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="color-scheme"]').content = theme;
})();
