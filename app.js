const HOURS = Array.from({ length: 18 }, (_, i) => i + 6);
const API = {
  zones: "/api/zones",
  bookings: "/api/bookings",
  metrics: "/api/metrics",
  export: "/api/bookings/export",
};

const state = {
  role: "client",
  date: new Date().toISOString().slice(0, 10),
  zones: [],
  bookings: [],
  editingId: null,
};

const el = {
  datePicker: document.querySelector("#datePicker"),
  rolePicker: document.querySelector("#rolePicker"),
  gridWrap: document.querySelector("#gridWrap"),
  bookingForm: document.querySelector("#bookingForm"),
  bookingId: document.querySelector("#bookingId"),
  zone: document.querySelector("#zone"),
  customerName: document.querySelector("#customerName"),
  phone: document.querySelector("#phone"),
  startHour: document.querySelector("#startHour"),
  duration: document.querySelector("#duration"),
  comment: document.querySelector("#comment"),
  status: document.querySelector("#status"),
  deleteBtn: document.querySelector("#deleteBtn"),
  resetBtn: document.querySelector("#resetBtn"),
  panelTitle: document.querySelector("#panelTitle"),
  bookingList: document.querySelector("#bookingList"),
  metrics: document.querySelector("#metrics"),
  exportBtn: document.querySelector("#exportBtn"),
  statusWrap: document.querySelector("#statusWrap"),
  tpl: document.querySelector("#bookingCardTpl"),
};

boot();

async function boot() {
  bindEvents();
  el.datePicker.value = state.date;
  el.rolePicker.value = state.role;
  await loadZones();
  resetForm();
  await loadDay();
}

function bindEvents() {
  el.datePicker.addEventListener("change", async () => {
    state.date = el.datePicker.value;
    resetForm();
    await loadDay();
  });

  el.rolePicker.addEventListener("change", () => {
    state.role = el.rolePicker.value;
    resetForm();
    render();
  });

  el.bookingForm.addEventListener("submit", onSubmit);
  el.resetBtn.addEventListener("click", resetForm);
  el.deleteBtn.addEventListener("click", deleteCurrent);
  el.exportBtn.addEventListener("click", exportCsv);
}

async function loadZones() {
  state.zones = await fetchJson(API.zones);
  el.zone.innerHTML = "";
  state.zones.forEach((z) => {
    const option = document.createElement("option");
    option.value = z.id;
    option.textContent = `${z.name} · ${z.price_hour} ₽/ч · ${z.capacity} чел`;
    el.zone.append(option);
  });
}

async function loadDay() {
  state.bookings = await fetchJson(`${API.bookings}?date=${encodeURIComponent(state.date)}`);
  const m = await fetchJson(`${API.metrics}?date=${encodeURIComponent(state.date)}`);
  render(m);
}

function render(metricsPayload = null) {
  renderGrid();
  renderList();

  if (metricsPayload) {
    renderMetrics(metricsPayload);
  }

  const admin = state.role === "admin";
  el.statusWrap.classList.toggle("hidden", !admin);
  el.deleteBtn.classList.toggle("hidden", !admin || !state.editingId);
}

function renderGrid() {
  const byKey = new Map();
  state.bookings.forEach((b) => {
    for (let h = b.start_hour; h < b.end_hour; h += 1) {
      byKey.set(`${b.zone_id}-${h}`, b);
    }
  });

  const grid = document.createElement("div");
  grid.className = "grid";

  const header = document.createElement("div");
  header.className = "row header";
  header.append(cell("Зона / Час", "cell zone-label"));
  HOURS.forEach((h) => header.append(cell(`${pad(h)}:00`, "cell")));
  grid.append(header);

  state.zones.forEach((z) => {
    const row = document.createElement("div");
    row.className = "row";
    row.append(cell(z.name, "cell zone-label"));

    HOURS.forEach((h) => {
      const existing = byKey.get(`${z.id}-${h}`);
      const c = document.createElement("div");
      c.className = `cell slot ${existing ? existing.status : "free"}`;
      c.dataset.zoneId = z.id;
      c.dataset.hour = h;

      if (existing) {
        c.title = `${existing.customer_name} (${pad(existing.start_hour)}:00-${pad(existing.end_hour)}:00)`;
        c.textContent = existing.start_hour === h ? existing.customer_name.split(" ")[0] : "";
      } else {
        c.title = "Свободно";
        c.textContent = "·";
      }

      c.addEventListener("click", () => onSlotClick(z.id, h, existing || null));
      row.append(c);
    });

    grid.append(row);
  });

  el.gridWrap.innerHTML = "";
  el.gridWrap.append(grid);
}

function onSlotClick(zoneId, hour, existing) {
  if (existing) {
    fillForm(existing);
    return;
  }

  fillForm({
    id: "",
    zone_id: zoneId,
    customer_name: "",
    phone: "",
    start_hour: hour,
    end_hour: hour + 2,
    status: "pending",
    comment: "",
  });
}

function fillForm(b) {
  state.editingId = b.id || null;
  el.bookingId.value = b.id || "";
  el.zone.value = b.zone_id;
  el.customerName.value = b.customer_name || "";
  el.phone.value = b.phone || "";
  el.startHour.value = b.start_hour;
  el.duration.value = Math.max(1, b.end_hour - b.start_hour);
  el.comment.value = b.comment || "";
  el.status.value = b.status || "pending";
  el.panelTitle.textContent = b.id ? `Редактирование #${b.id}` : "Новая бронь";
  el.deleteBtn.classList.toggle("hidden", !(state.role === "admin" && b.id));
}

function resetForm() {
  state.editingId = null;
  el.bookingForm.reset();
  if (state.zones[0]) {
    el.zone.value = String(state.zones[0].id);
  }
  el.startHour.value = "8";
  el.duration.value = "2";
  el.status.value = "pending";
  el.panelTitle.textContent = "Новая бронь";
  el.deleteBtn.classList.add("hidden");
}

async function onSubmit(e) {
  e.preventDefault();
  const payload = {
    date: state.date,
    zone_id: Number(el.zone.value),
    customer_name: el.customerName.value.trim(),
    phone: el.phone.value.trim(),
    start_hour: Number(el.startHour.value),
    duration: Number(el.duration.value),
    comment: el.comment.value.trim(),
    status: state.role === "admin" ? el.status.value : "pending",
  };

  try {
    if (state.editingId) {
      await fetchJson(`${API.bookings}/${state.editingId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      await fetchJson(API.bookings, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }

    resetForm();
    await loadDay();
  } catch (err) {
    alert(err.message);
  }
}

async function deleteCurrent() {
  if (!state.editingId || state.role !== "admin") return;
  if (!confirm(`Удалить бронь #${state.editingId}?`)) return;

  try {
    await fetchJson(`${API.bookings}/${state.editingId}`, { method: "DELETE" });
    resetForm();
    await loadDay();
  } catch (err) {
    alert(err.message);
  }
}

function renderList() {
  el.bookingList.innerHTML = "";
  if (!state.bookings.length) {
    el.bookingList.textContent = "На эту дату броней пока нет.";
    return;
  }

  state.bookings.forEach((b) => {
    const card = el.tpl.content.firstElementChild.cloneNode(true);
    const zone = state.zones.find((z) => z.id === b.zone_id);
    card.querySelector(".line1").textContent = `#${b.id} · ${zone?.name || b.zone_id}`;
    card.querySelector(".line2").textContent = `${b.customer_name} · ${b.phone}`;
    card.querySelector(".line3").textContent = `${pad(b.start_hour)}:00–${pad(b.end_hour)}:00 · ${b.status}`;
    card.addEventListener("click", () => fillForm(b));
    el.bookingList.append(card);
  });
}

function renderMetrics(m) {
  el.metrics.innerHTML = `
    <li>Броней: <b>${m.bookings}</b></li>
    <li>Загрузка: <b>${m.load_pct}%</b></li>
    <li>Выручка (план): <b>${Number(m.revenue).toLocaleString("ru-RU")} ₽</b></li>
    <li>Pending: <b>${m.pending}</b></li>
    <li>Confirmed: <b>${m.confirmed}</b></li>
    <li>Paid: <b>${m.paid}</b></li>
  `;
}

function exportCsv() {
  window.open(`${API.export}?date=${encodeURIComponent(state.date)}`, "_blank");
}

function cell(text, className = "cell") {
  const d = document.createElement("div");
  d.className = className;
  d.textContent = text;
  return d;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      // ignore
    }
    throw new Error(detail);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return null;
}
