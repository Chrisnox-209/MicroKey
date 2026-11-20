"use strict";
import { generatePassword } from "./password-generator.mjs";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const csrf = $('meta[name="csrf-token"]').content;
const pinNames = new Map([...$("#trigger-pin").options].map((option) => [option.value, option.textContent.split(" · ")[0]]));
let currentState = null;
let currentDevice = null;
let currentPort = "";
let submitting = false;
let lastCompletedJob = null;
let pollTimer = null;
let refreshing = false;
let boardChosenManually = false;
let resetGuide = false;
let copyingPassword = false;
$("#theme-switch").checked = document.documentElement.dataset.theme === "dark";
$("#theme-switch").addEventListener("change", () => {
  const theme = $("#theme-switch").checked ? "dark" : "light";
  document.documentElement.dataset.theme = theme;
  $('meta[name="color-scheme"]').content = theme;
  try { localStorage.setItem("microkey-theme-spotlight", theme); } catch (_) {}
});

function showView(view) {
  $$(".tab").forEach((tab) => {
    const selected = tab.dataset.view === view;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  $$(".tab-view").forEach((panel) => { panel.hidden = panel.id !== `view-${view}`; });
  updateTriggerPreview();
}

function notice(message, error = false) {
  $("#notice").textContent = message;
  $("#notice").classList.toggle("error", error);
  $("#notice").hidden = false;
}

function triggerMode() { return $('input[name="trigger-mode"]:checked').value; }

function updateTriggerPreview() {
  const mode = triggerMode();
  const usesButton = mode !== "usb";
  const pin = $("#trigger-pin").value;
  const label = pinNames.get(pin) || "D4";
  $("#pin-settings").hidden = !usesButton;
  $("#wiring-card").hidden = !usesButton || resetGuide;
  $("#usb-explanation").hidden = usesButton || resetGuide;
  $("#reset-guide").hidden = !resetGuide;
  $("#toggle-reset-guide").setAttribute("aria-pressed", String(resetGuide));
  $("#toggle-reset-guide").lastChild.textContent = resetGuide ? " Masquer le repère RESET" : " Afficher le repère RESET";
  $("#boot-delay-setting").hidden = mode === "button";
  $("#board-visual").classList.toggle("button-active", usesButton);
  $("#board-visual").classList.toggle("show-reset", resetGuide);
  $(".board-status").classList.toggle("reset-status", resetGuide);
  $("#pin-inline-label").textContent = label;
  $("#wire-pin").textContent = label;
  $("#board-mode-label").textContent = resetGuide ? "AIDE RESET" : {usb: "USB", button: "BOUTON", both: "USB + BOUTON"}[mode];
  $("#selection-description").textContent = resetGuide ? "RESET : RST ↔ GND, deux contacts rapides" : mode === "usb" ? "Saisie automatique au branchement" : mode === "button" ? `Un appui sur ${label}, une saisie` : `Au branchement ou avec le bouton sur ${label}`;
  $("#test-instruction").textContent = mode === "usb" ? "Rebranchez la carte. Elle tape après le délai choisi." : mode === "button" ? `Rebranchez la carte, puis appuyez sur le bouton relié à ${label} et GND.` : `Rebranchez pour la saisie automatique, ou appuyez sur le bouton relié à ${label} et GND.`;
  $$(".diagram-pin[data-pin]").forEach((element) => {
    const selected = usesButton && !resetGuide && element.dataset.pin === pin;
    element.classList.toggle("selected", selected);
    element.setAttribute("aria-pressed", String(selected));
  });
}

function updateButtons() {
  const busy = submitting || currentState?.job.status === "running";
  const port = $("#port").value;
  const selected = Boolean(port);
  const known = Boolean(selected && currentDevice && currentPort === port);
  const suggested = currentState?.ports.find((entry) => entry.port === port)?.suggested_board;
  const mismatch = Boolean(suggested && $("#board").value && suggested !== $("#board").value);
  $("#save-button").disabled = busy || !known;
  $("#clear-button").disabled = busy || !known || !currentDevice.configured;
  $("#read-button").disabled = busy || !selected;
  $("#flash-button").disabled = busy || !selected || !$("#board").value || !currentState?.tools.installed || mismatch;
  $("#recover-button").disabled = busy || !$("#board").value || !currentState?.tools.installed || mismatch;
  ["#install-button", "#port", "#board", "#refresh-button"].forEach((selector) => { $(selector).disabled = busy; });
  $("#read-button").firstChild.textContent = known ? "Actualiser l’état " : "Connecter ";
  $("#save-button").firstChild.textContent = busy && currentState?.job.kind === "configure" ? "Enregistrement… " : "Enregistrer sur la carte ";
  $("#board-profile-hint").textContent = suggested ? `Profil USB reconnu : ${suggested === "5v16" ? "5 V / 16 MHz" : "3,3 V / 8 MHz"}.${mismatch ? " Sélectionnez cette variante pour continuer." : ""}` : "Vérifiez l’inscription sur la carte avant de flasher.";
}

function resetDevice() {
  currentDevice = null;
  currentPort = "";
  $("#password").required = true;
  $("#password").placeholder = "Le mot de passe que la carte doit taper";
  $("#password-help").textContent = "1 à 128 caractères : lettres sans accent, chiffres, espaces et symboles ASCII.";
  $("#device-state").textContent = "Connectez la carte pour lire son état, sans relire le mot de passe.";
  $("#config-status").textContent = "Connectez la carte ou installez son firmware pour commencer.";
  updateButtons();
}

function showDevice(result) {
  if (!result?.device) return;
  currentDevice = result.device;
  currentPort = result.port;
  if ([...$("#port").options].some((option) => option.value === result.port)) $("#port").value = result.port;
  const info = result.device;
  $("#device-state").textContent = `Firmware ${info.firmware || "connecté"} · ${info.configured ? `${info.length} caractères enregistrés` : "Aucun mot de passe enregistré"}.`;
  $("#config-status").textContent = info.configured ? "Carte prête. Modifiez vos réglages, puis enregistrez." : "Carte prête. Ajoutez votre premier mot de passe.";
  $("#password").required = !info.configured;
  if (info.configured) {
    $("#password").placeholder = "Laisser vide pour garder le mot de passe actuel";
    $("#password-help").textContent = `${info.length} caractères sont déjà enregistrés. Laissez ce champ vide pour modifier uniquement les réglages.`;
    $("#layout").value = info.layout === "us" ? "us" : "fr";
    $("#delay").value = info.delay_ms / 1000;
    $("#interval").value = info.interval_ms;
    $("#press-enter").checked = Boolean(info.press_enter);
    const mode = ["usb", "button", "both"].includes(info.trigger_mode) ? info.trigger_mode : "usb";
    $(`input[name="trigger-mode"][value="${mode}"]`).checked = true;
    $("#trigger-pin").value = pinNames.has(String(info.trigger_pin)) ? String(info.trigger_pin) : "4";
  }
  updateTriggerPreview();
}

function renderState(data) {
  currentState = data;
  const select = $("#port");
  const previous = select.value;
  const signature = JSON.stringify(data.ports.map((port) => [port.port, port.name, port.suggested_board]));
  if (select.dataset.signature !== signature) {
    select.dataset.signature = signature;
    select.replaceChildren(new Option(data.ports.length ? "Choisir un port…" : "Aucun port USB détecté", ""));
    for (const port of data.ports) select.add(new Option(`${port.port} · ${port.name}`, port.port));
    select.value = data.ports.some((port) => port.port === previous) ? previous : data.ports.length === 1 ? data.ports[0].port : "";
    if (currentPort && !data.ports.some((port) => port.port === currentPort)) resetDevice();
  }
  const selectedPort = data.ports.find((port) => port.port === select.value);
  if (selectedPort?.suggested_board && !boardChosenManually) $("#board").value = selectedPort.suggested_board;
  $("#connection-indicator").classList.toggle("connected", Boolean(selectedPort));
  $("#board-visual").classList.toggle("board-connected", Boolean(selectedPort));
  $("#connection-title").textContent = selectedPort ? "Pro Micro détecté" : "Aucune carte détectée";
  $("#device-name").textContent = selectedPort?.name || "Branchez votre Pro Micro avec un câble USB de données";
  $("#tools-badge").textContent = data.tools.installed ? "Prêts" : "À installer";
  $("#install-button").firstChild.textContent = data.tools.installed ? "Réinstaller les outils " : "Installer les outils ";
  const job = data.job;
  $("#job-status").textContent = {idle: "Prêt", running: "En cours…", success: "Terminé", error: "Échec"}[job.status] || "Prêt";
  if (job.logs.length || job.error) {
    const output = $("#log");
    const atBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 40;
    output.textContent = job.logs.join("\n\n") + (job.error ? `\n\nErreur : ${job.error}` : "");
    if (atBottom) output.scrollTop = output.scrollHeight;
  }
  if (job.status === "running") {
    $("#journal").open = true;
    if (job.kind === "recover" && job.logs.some((line) => line.includes("Récupération prête")) && !job.logs.some((line) => line.includes("Bootloader détecté"))) notice("Récupération prête. Carte branchée, faites deux contacts rapides entre RST et GND, ou deux appuis rapides sur RESET.");
  }
  if (job.id && job.status !== "running" && job.id !== lastCompletedJob) {
    lastCompletedJob = job.id;
    if (job.status === "error") {
      notice(job.error, true);
      $("#journal").open = true;
    } else {
      showDevice(job.result);
      const messages = {tools: "Outils installés. Choisissez votre variante, puis flashez le firmware.", flash: "Firmware installé et vérifié. Passez à Configurer pour régler la carte.", recover: "Carte récupérée et firmware vérifié. Vous pouvez maintenant configurer son fonctionnement.", configure: "Configuration enregistrée. Débranchez puis rebranchez la carte pour activer vos réglages.", info: "Carte connectée. Débranchez puis rebranchez avant de tester la saisie.", clear: "Mot de passe effacé. La carte ne tape plus rien."};
      notice(messages[job.kind] || "Opération terminée.");
      if (["flash", "recover"].includes(job.kind)) showView("configure");
    }
  }
  updateButtons();
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  clearTimeout(pollTimer);
  try {
    const response = await fetch("/api/state", {cache: "no-store"});
    if (!response.ok) throw new Error("Le serveur local ne répond pas. Relancez-le avec make run.");
    renderState(await response.json());
  } catch (error) {
    notice(error.message || "Connexion au serveur interrompue.", true);
  } finally {
    refreshing = false;
    pollTimer = setTimeout(refresh, currentState?.job.status === "running" ? 700 : 4000);
  }
}

async function operation(path, data = {}) {
  if (submitting || currentState?.job.status === "running") return;
  submitting = true;
  updateButtons();
  try {
    const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf}, body: JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Impossible de démarrer cette opération.");
    if (path === "/api/configure") {
      $("#password").value = "";
      $("#password").type = "password";
      $("#toggle-password").textContent = "Voir";
      $("#toggle-password").setAttribute("aria-label", "Afficher le mot de passe");
      $("#toggle-password").setAttribute("aria-pressed", "false");
      updatePasswordCount();
      data.password = "";
    }
    notice("Opération en cours. Gardez la carte branchée.");
    $("#journal").open = true;
    await refresh();
  } catch (error) {
    notice(error.message, true);
  } finally {
    submitting = false;
    updateButtons();
  }
}

function updatePasswordCount() {
  const length = $("#password").value.length;
  $("#password-count").textContent = `${length} / 128`;
  $("#copy-password").disabled = length === 0 || copyingPassword;
  $("#copy-feedback").textContent = "";
}
function updateGeneratorHelp() {
  const dualLayout = $("#generator-compatible").checked;
  const symbols = $("#generator-symbols").checked;
  $("#generator-help").textContent = dualLayout
    ? "Même saisie sur AZERTY français PC et QWERTY US : sans chiffres ni lettres A/Q/W/Z/M." + (symbols ? " Symboles limités à + et =." : " Sans symboles.")
    : "Lettres et chiffres" + (symbols ? " avec symboles." : ".") + " Choisissez le clavier de l’ordinateur cible ci-dessous.";
}
$$(".tab").forEach((tab, index, tabs) => {
  tab.addEventListener("click", () => { showView(tab.dataset.view); $("#atelier").scrollIntoView({behavior: "smooth", block: "start"}); });
  tab.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault(); showView(tabs[next].dataset.view); tabs[next].focus();
  });
});
$(".brand").addEventListener("click", () => showView("configure"));
$("#open-workspace").addEventListener("click", () => showView("configure"));
$("#open-configurator").addEventListener("click", () => showView("configure"));
$("#open-installer").addEventListener("click", () => showView("install"));
$$('input[name="trigger-mode"]').forEach((input) => input.addEventListener("change", () => { resetGuide = false; updateTriggerPreview(); }));
$("#trigger-pin").addEventListener("change", () => { resetGuide = false; updateTriggerPreview(); });
$("#toggle-reset-guide").addEventListener("click", () => { resetGuide = !resetGuide; updateTriggerPreview(); });
$(".recovery-options").addEventListener("toggle", () => { resetGuide = $(".recovery-options").open; updateTriggerPreview(); });
$$(".diagram-pin[data-pin]").forEach((pin) => {
  const selectPin = () => {
    resetGuide = false;
    $("#trigger-pin").value = pin.dataset.pin;
    if (triggerMode() === "usb") $('input[name="trigger-mode"][value="button"]').checked = true;
    updateTriggerPreview();
  };
  pin.addEventListener("click", selectPin);
  pin.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); selectPin(); } });
});
$("#password").addEventListener("input", updatePasswordCount);
["#generator-compatible", "#generator-symbols", "#generator-length"].forEach((selector) => {
  $(selector).addEventListener("change", () => {
    updateGeneratorHelp();
    $("#generation-feedback").textContent = "Options modifiées · cliquez sur Générer pour les appliquer au prochain mot de passe.";
  });
});
$("#generate-password").addEventListener("click", () => {
  try {
    const dualLayout = $("#generator-compatible").checked;
    const password = generatePassword(Number($("#generator-length").value), {symbols: $("#generator-symbols").checked, dualLayout});
    $("#password").value = password;
    $("#password").type = "password";
    $("#toggle-password").textContent = "Voir";
    $("#toggle-password").setAttribute("aria-label", "Afficher le mot de passe");
    $("#toggle-password").setAttribute("aria-pressed", "false");
    updatePasswordCount();
    $("#generation-feedback").textContent = `${password.length} caractères générés localement${dualLayout ? " · compatibles AZERTY + QWERTY" : " · pour le clavier cible choisi"}. Enregistrez sur la carte pour les appliquer.`;
  } catch (error) { notice(error.message, true); }
});
$("#toggle-password").addEventListener("click", () => {
  const visible = $("#password").type === "password";
  $("#password").type = visible ? "text" : "password";
  $("#toggle-password").textContent = visible ? "Masquer" : "Voir";
  $("#toggle-password").setAttribute("aria-label", visible ? "Masquer le mot de passe" : "Afficher le mot de passe");
  $("#toggle-password").setAttribute("aria-pressed", String(visible));
});
$("#copy-password").addEventListener("click", async () => {
  const password = $("#password").value;
  if (!password || copyingPassword) return;
  copyingPassword = true;
  $("#copy-password").disabled = true;
  $("#copy-password").textContent = "Copie…";
  $("#copy-feedback").textContent = "";
  try {
    await navigator.clipboard.writeText(password);
    if ($("#password").value === password) $("#copy-feedback").textContent = "Mot de passe copié dans le presse-papiers.";
  } catch (_) {
    if ($("#password").value === password) $("#copy-feedback").textContent = "Copie refusée par le navigateur. Affichez le mot de passe pour le copier manuellement.";
  } finally {
    copyingPassword = false;
    $("#copy-password").textContent = "Copier";
    $("#copy-password").disabled = $("#password").value.length === 0;
  }
});
$("#port").addEventListener("change", () => { resetDevice(); if (currentState) renderState(currentState); });
$("#board").addEventListener("change", () => { boardChosenManually = true; updateButtons(); });
$("#refresh-button").addEventListener("click", refresh);
$("#read-button").addEventListener("click", () => operation("/api/device", {port: $("#port").value}));
$("#install-button").addEventListener("click", () => operation("/api/tools"));
$("#recover-button").addEventListener("click", () => {
  const label = $("#board").selectedOptions[0].textContent;
  if (window.confirm(`Récupérer la carte en ${label} ? Le programme sera remplacé. Quand le journal affiche « Récupération prête », faites deux contacts rapides entre RST et GND ou deux appuis sur RESET.`)) {
    resetDevice(); operation("/api/recover", {board: $("#board").value});
  }
});
$("#flash-button").addEventListener("click", () => {
  $("#flash-port").textContent = $("#port").value;
  $("#flash-board").textContent = $("#board").selectedOptions[0].textContent;
  $("#flash-dialog").showModal();
});
$("#cancel-flash").addEventListener("click", () => $("#flash-dialog").close());
$("#confirm-flash").addEventListener("click", () => {
  $("#flash-dialog").close(); resetDevice();
  operation("/api/flash", {port: $("#port").value, board: $("#board").value});
});
$("#config-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const password = $("#password").value;
  if (password && !/^[\x20-\x7e]{1,128}$/.test(password)) {
    notice("Utilisez des caractères ASCII imprimables, sans accents ni emoji.", true); return;
  }
  operation("/api/configure", {port: $("#port").value, password, layout: $("#layout").value, delay_ms: Number($("#delay").value) * 1000, interval_ms: Number($("#interval").value), press_enter: $("#press-enter").checked, trigger_mode: triggerMode(), trigger_pin: Number($("#trigger-pin").value)});
});
$("#clear-button").addEventListener("click", () => {
  if (window.confirm("Effacer définitivement le mot de passe enregistré sur cette carte ?")) operation("/api/clear", {port: $("#port").value});
});
$("#test-input").addEventListener("input", () => { $("#test-count").textContent = `${$("#test-input").value.length} caractère(s) reçu(s)`; });
$("#test-input").addEventListener("keydown", (event) => { if (event.key === "Enter") event.preventDefault(); });
$("#clear-test").addEventListener("click", () => { $("#test-input").value = ""; $("#test-count").textContent = "0 caractère reçu"; });
updateTriggerPreview();
updateGeneratorHelp();
updatePasswordCount();
refresh();
