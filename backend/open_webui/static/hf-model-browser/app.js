const state = {
  selectedModel: null,
  filters: {
    q: "",
    tags: [],
    formats: [],
    quantizations: [],
    favorites_only: false,
    compatible_only: false,
    sort: "newest",
  },
  availableFilters: {
    tags: ["RAG", "chat", "agent"],
    formats: ["GGUF", "GGML"],
    quantizations: ["4bit", "8bit"],
  },
};

const elements = {
  cards: document.getElementById("cards"),
  resultCount: document.getElementById("resultCount"),
  catalogStatus: document.getElementById("catalogStatus"),
  searchInput: document.getElementById("searchInput"),
  suggestions: document.getElementById("modelSuggestions"),
  favoritesOnly: document.getElementById("favoritesOnly"),
  compatibleOnly: document.getElementById("compatibleOnly"),
  sortSelect: document.getElementById("sortSelect"),
  tagFilters: document.getElementById("tagFilters"),
  formatFilters: document.getElementById("formatFilters"),
  quantizationFilters: document.getElementById("quantizationFilters"),
  savedFilters: document.getElementById("savedFilters"),
  saveFilterButton: document.getElementById("saveFilterButton"),
  syncCatalogButton: document.getElementById("syncCatalogButton"),
  emptyState: document.getElementById("emptyState"),
  selectedModelLabel: document.getElementById("selectedModelLabel"),
  templateSelect: document.getElementById("templateSelect"),
  memoryToggle: document.getElementById("memoryToggle"),
  toolsInput: document.getElementById("toolsInput"),
  deploymentForm: document.getElementById("deploymentForm"),
  deploymentError: document.getElementById("deploymentError"),
  configOutput: document.getElementById("configOutput"),
  dockerfileOutput: document.getElementById("dockerfileOutput"),
  composeOutput: document.getElementById("composeOutput"),
  notesOutput: document.getElementById("notesOutput"),
};

function debounce(fn, wait = 250) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), wait);
  };
}

function formatDate(value) {
  if (!value) {
    return "Ukendt";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("da-DK", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function buildChips(container, values, selectedValues, onToggle) {
  container.innerHTML = "";
  for (const value of values) {
    const chip = document.createElement("label");
    chip.className = "chip";
    chip.innerHTML = `
      <input type="checkbox" ${selectedValues.includes(value) ? "checked" : ""} />
      <span>${value}</span>
    `;
    chip.querySelector("input").addEventListener("change", () => onToggle(value));
    container.appendChild(chip);
  }
}

function toggleSelection(list, value) {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const errorPayload = await response.json();
      detail = errorPayload.detail || detail;
    } catch (error) {
      detail = await response.text() || detail;
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function buildQueryString() {
  const params = new URLSearchParams();
  if (state.filters.q) {
    params.set("q", state.filters.q);
  }
  for (const tag of state.filters.tags) {
    params.append("tags", tag);
  }
  for (const format of state.filters.formats) {
    params.append("formats", format);
  }
  for (const quantization of state.filters.quantizations) {
    params.append("quantizations", quantization);
  }
  params.set("favorites_only", String(state.filters.favorites_only));
  params.set("compatible_only", String(state.filters.compatible_only));
  params.set("sort", state.filters.sort);
  params.set("limit", "60");
  return params.toString();
}

function setStatus(message) {
  elements.catalogStatus.textContent = message;
}

function setDeploymentError(message) {
  elements.deploymentError.textContent = message;
  elements.deploymentError.classList.toggle("hidden", !message);
}

async function loadModels() {
  setStatus("Henter modeller fra databasen...");
  const payload = await fetchJson(`/api/v1/hf-models?${buildQueryString()}`);
  state.availableFilters = payload.available_filters;
  renderFilterGroups();
  renderCards(payload.items);
  elements.resultCount.textContent = String(payload.total);
  elements.emptyState.classList.toggle("hidden", payload.items.length > 0);
  const syncStamp = payload.last_synced_at ? `Senest synkroniseret: ${formatDate(payload.last_synced_at)}` : "Ingen synkronisering endnu";
  setStatus(syncStamp);
}

async function loadAutocomplete() {
  const query = elements.searchInput.value.trim();
  if (query.length < 2) {
    elements.suggestions.innerHTML = "";
    return;
  }
  const suggestions = await fetchJson(`/api/v1/hf-models/autocomplete?q=${encodeURIComponent(query)}`);
  elements.suggestions.innerHTML = suggestions.map((item) => `<option value="${item}"></option>`).join("");
}

function renderCards(items) {
  elements.cards.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "card";
    const tags = item.tags.map((tag) => `<span class="pill">${tag}</span>`).join("");
    const compatibilityClass = item.llama_cpp_compatible ? "compatible" : "incompatible";
    const compatibilityText = item.llama_cpp_compatible ? "Kompatibel" : "Inkompatibel";
    const tooltip = item.llama_cpp_compatible ? "" : 'title="Ikke kompatibel med Llama.cpp"';

    card.innerHTML = `
      <div class="card-header">
        <div>
          <h3>${item.model_id}</h3>
          <div class="meta">
            <span class="compatibility ${compatibilityClass}" ${tooltip}>${compatibilityText}</span>
            <span class="pill">${item.format || "Ukendt format"}</span>
            <span class="pill">${item.quantization || "Ukendt kvantisering"}</span>
          </div>
        </div>
        <button class="favorite-button ${item.is_favorite ? "active" : ""}" title="Favorit">
          ${item.is_favorite ? "★" : "☆"}
        </button>
      </div>
      <div class="meta">${tags || '<span class="muted">Ingen tags</span>'}</div>
      <div class="muted">
        <div>Størrelse: ${item.size || "Ukendt"}</div>
        <div>Uploadet: ${formatDate(item.upload_date)}</div>
      </div>
      <div class="card-actions">
        <a class="secondary link-button" href="${item.huggingface_url}" target="_blank" rel="noreferrer">Hugging Face</a>
        <button class="deploy-button" ${item.llama_cpp_compatible ? "" : "disabled"}>Deploy</button>
      </div>
    `;

    card.querySelector(".favorite-button").addEventListener("click", async () => {
      await fetchJson("/api/v1/hf-models/favorites", {
        method: "POST",
        body: JSON.stringify({
          model_id: item.model_id,
          favorite: !item.is_favorite,
        }),
      });
      await loadModels();
    });

    card.querySelector(".deploy-button")?.addEventListener("click", async () => {
      await selectModel(item.model_id);
    });

    elements.cards.appendChild(card);
  }
}

async function selectModel(modelId) {
  state.selectedModel = modelId;
  elements.selectedModelLabel.textContent = modelId;
  setDeploymentError("");

  // Validate format and quantization before enabling template/deployment generation.
  await fetchJson("/api/v1/hf-models/validate-selection", {
    method: "POST",
    body: JSON.stringify({ model_id: modelId }),
  });
}

function renderFilterGroups() {
  buildChips(elements.tagFilters, state.availableFilters.tags, state.filters.tags, async (value) => {
    state.filters.tags = toggleSelection(state.filters.tags, value);
    await loadModels();
  });
  buildChips(elements.formatFilters, state.availableFilters.formats, state.filters.formats, async (value) => {
    state.filters.formats = toggleSelection(state.filters.formats, value);
    await loadModels();
  });
  buildChips(
    elements.quantizationFilters,
    state.availableFilters.quantizations,
    state.filters.quantizations,
    async (value) => {
      state.filters.quantizations = toggleSelection(state.filters.quantizations, value);
      await loadModels();
    }
  );
}

async function loadSavedFilters() {
  const filters = await fetchJson("/api/v1/hf-models/saved-filters");
  elements.savedFilters.innerHTML = "";

  if (filters.length === 0) {
    elements.savedFilters.innerHTML = '<p class="muted">Ingen gemte filtre endnu.</p>';
    return;
  }

  for (const savedFilter of filters) {
    const wrapper = document.createElement("div");
    wrapper.className = "saved-filter";
    wrapper.innerHTML = `
      <div>
        <strong>${savedFilter.name}</strong>
        <div class="muted">${savedFilter.filters.sort || "newest"} · ${savedFilter.filters.tags?.join(", ") || "ingen tags"}</div>
      </div>
      <div class="saved-filter-actions">
        <button class="secondary small apply-filter">Brug</button>
        <button class="secondary small delete-filter">Slet</button>
      </div>
    `;

    wrapper.querySelector(".apply-filter").addEventListener("click", async () => {
      Object.assign(state.filters, savedFilter.filters);
      syncFormControls();
      await loadModels();
    });

    wrapper.querySelector(".delete-filter").addEventListener("click", async () => {
      await fetchJson(`/api/v1/hf-models/saved-filters/${encodeURIComponent(savedFilter.name)}`, {
        method: "DELETE",
      });
      await loadSavedFilters();
    });

    elements.savedFilters.appendChild(wrapper);
  }
}

function syncFormControls() {
  elements.searchInput.value = state.filters.q;
  elements.favoritesOnly.checked = state.filters.favorites_only;
  elements.compatibleOnly.checked = state.filters.compatible_only;
  elements.sortSelect.value = state.filters.sort;
  renderFilterGroups();
}

async function saveCurrentFilter() {
  const name = window.prompt("Navn på filter");
  if (!name) {
    return;
  }

  await fetchJson("/api/v1/hf-models/saved-filters", {
    method: "POST",
    body: JSON.stringify({
      name,
      filters: state.filters,
    }),
  });
  await loadSavedFilters();
}

async function syncCatalog() {
  setStatus("Synkroniserer med Hugging Face...");
  await fetchJson("/api/v1/hf-models/sync", {
    method: "POST",
  });
  await loadModels();
}

async function generateBundle(event) {
  event.preventDefault();
  setDeploymentError("");

  if (!state.selectedModel) {
    setDeploymentError("Vælg en kompatibel model, før deploy bundle kan genereres.");
    return;
  }

  const tools = elements.toolsInput.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  const payload = {
    template: elements.templateSelect.value,
    model: state.selectedModel,
    memory: elements.memoryToggle.checked,
    tools,
  };

  try {
    // Bundle generation always validates the selected model against the catalog DB.
    const bundle = await fetchJson("/api/v1/hf-models/deployment-bundle", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.configOutput.textContent = bundle.config_json;
    elements.dockerfileOutput.textContent = bundle.dockerfile;
    elements.composeOutput.textContent = bundle.compose_file;
    elements.notesOutput.textContent = bundle.runtime_notes.join("\n");
  } catch (error) {
    setDeploymentError(error.message);
  }
}

function wireEvents() {
  elements.searchInput.addEventListener(
    "input",
    debounce(async () => {
      state.filters.q = elements.searchInput.value.trim();
      await Promise.all([loadAutocomplete(), loadModels()]);
    })
  );

  elements.favoritesOnly.addEventListener("change", async () => {
    state.filters.favorites_only = elements.favoritesOnly.checked;
    await loadModels();
  });

  elements.compatibleOnly.addEventListener("change", async () => {
    state.filters.compatible_only = elements.compatibleOnly.checked;
    await loadModels();
  });

  elements.sortSelect.addEventListener("change", async () => {
    state.filters.sort = elements.sortSelect.value;
    await loadModels();
  });

  elements.saveFilterButton.addEventListener("click", saveCurrentFilter);
  elements.syncCatalogButton.addEventListener("click", async () => {
    try {
      await syncCatalog();
    } catch (error) {
      setStatus(`Kunne ikke synkronisere: ${error.message}`);
    }
  });
  elements.deploymentForm.addEventListener("submit", generateBundle);
}

async function init() {
  wireEvents();
  syncFormControls();
  try {
    await Promise.all([loadModels(), loadSavedFilters()]);
  } catch (error) {
    setStatus(`Kunne ikke hente modelkatalog: ${error.message}`);
  }
}

window.addEventListener("DOMContentLoaded", init);
