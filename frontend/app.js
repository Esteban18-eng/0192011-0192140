const config = window.HUELLAS_CONFIG || {};
const PETS_API = (config.petsApiUrl || "http://localhost:8001").replace(/\/$/, "");
const ADOPTIONS_API = (config.adoptionsApiUrl || "http://localhost:8002").replace(/\/$/, "");
const petCache = new Map();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

async function request(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  } catch {
    throw new Error("No se pudo conectar con el servicio. Verifica que las APIs estén activas.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Ocurrió un error inesperado.";
    throw new Error(detail);
  }
  return body;
}

function showMessage(element, message, kind = "") {
  element.textContent = message;
  element.className = `message ${kind}`.trim();
}

function showFormMessage(form, message, kind = "") {
  const element = form.querySelector(".form-message");
  element.textContent = message;
  element.className = `form-message ${kind}`.trim();
}

async function loadPets() {
  const message = document.querySelector("#petsMessage");
  const list = document.querySelector("#petList");
  const select = document.querySelector("#petSelect");
  showMessage(message, "Cargando mascotas…");
  try {
    const allPets = await request(`${PETS_API}/pets?available_only=false`);
    const pets = allPets.filter((pet) => pet.status === "available");
    petCache.clear();
    allPets.forEach((pet) => petCache.set(pet.id, pet));
    list.innerHTML = pets.length ? pets.map((pet) => {
      const image = pet.photo_url
        ? `<img src="${escapeHtml(pet.photo_url)}" alt="Foto de ${escapeHtml(pet.name)}" loading="lazy">`
        : '<div class="pet-placeholder" aria-hidden="true">🐾</div>';
      return `<article class="pet-card">${image}<div class="pet-body">
        <h3>${escapeHtml(pet.name)}</h3>
        <div class="pet-meta">${escapeHtml(pet.species)} · ${escapeHtml(pet.breed)} · ${pet.age} años</div>
        <p>${escapeHtml(pet.description)}</p>
        <button class="button apply-button" type="button" data-pet-id="${pet.id}">Quiero adoptar</button>
      </div></article>`;
    }).join("") : '<p class="message">Aún no hay mascotas disponibles. Vuelve pronto.</p>';
    select.innerHTML = '<option value="">Selecciona una mascota</option>' + pets
      .map((pet) => `<option value="${pet.id}">${escapeHtml(pet.name)} (${escapeHtml(pet.species)})</option>`)
      .join("");
    showMessage(message, `${pets.length} mascota${pets.length === 1 ? "" : "s"} disponible${pets.length === 1 ? "" : "s"}.`);
  } catch (error) {
    list.replaceChildren();
    showMessage(message, error.message, "error");
  }
}

async function loadAdoptions() {
  const message = document.querySelector("#adoptionsMessage");
  const list = document.querySelector("#adoptionList");
  showMessage(message, "Cargando solicitudes…");
  try {
    const adoptions = await request(`${ADOPTIONS_API}/adoptions`);
    list.innerHTML = adoptions.length ? adoptions.map((adoption) => {
      const pet = petCache.get(adoption.pet_id);
      const petName = pet ? pet.name : `Mascota #${adoption.pet_id}`;
      const actions = adoption.status === "pending"
        ? `<div class="adoption-actions">
            <button class="button approve-button" data-id="${adoption.id}" type="button">Aprobar</button>
            <button class="button button-danger reject-button" data-id="${adoption.id}" type="button">Rechazar</button>
          </div>`
        : "";
      return `<article class="adoption-card">
        <h3>${escapeHtml(adoption.applicant_name)} · ${escapeHtml(petName)}</h3>
        <span class="status ${escapeHtml(adoption.status)}">${escapeHtml(adoption.status)}</span>
        <p>${escapeHtml(adoption.email)} · ${escapeHtml(adoption.phone)}</p>
        <p>${escapeHtml(adoption.motivation)}</p>${actions}
      </article>`;
    }).join("") : '<p class="message">Todavía no hay solicitudes registradas.</p>';
    showMessage(message, `${adoptions.length} solicitud${adoptions.length === 1 ? "" : "es"}.`);
  } catch (error) {
    list.replaceChildren();
    showMessage(message, error.message, "error");
  }
}

document.querySelector("#petList").addEventListener("click", (event) => {
  const button = event.target.closest(".apply-button");
  if (!button) return;
  document.querySelector("#petSelect").value = button.dataset.petId;
  document.querySelector("#adoptionForm").scrollIntoView({ behavior: "smooth", block: "center" });
});

document.querySelector("#refreshPets").addEventListener("click", loadPets);
document.querySelector("#refreshAdoptions").addEventListener("click", loadAdoptions);

document.querySelector("#petForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const data = Object.fromEntries(new FormData(form));
  data.age = Number(data.age);
  if (!data.photo_url) delete data.photo_url;
  button.disabled = true;
  try {
    await request(`${PETS_API}/pets`, { method: "POST", body: JSON.stringify(data) });
    form.reset();
    form.elements.breed.value = "Mestizo";
    showFormMessage(form, "Mascota registrada correctamente.", "success");
    await loadPets();
  } catch (error) {
    showFormMessage(form, error.message, "error");
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#adoptionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const data = Object.fromEntries(new FormData(form));
  data.pet_id = Number(data.pet_id);
  button.disabled = true;
  try {
    await request(`${ADOPTIONS_API}/adoptions`, { method: "POST", body: JSON.stringify(data) });
    form.reset();
    showFormMessage(form, "Solicitud enviada. La fundación hará seguimiento.", "success");
    await loadAdoptions();
  } catch (error) {
    showFormMessage(form, error.message, "error");
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#adoptionList").addEventListener("click", async (event) => {
  const button = event.target.closest(".approve-button, .reject-button");
  if (!button) return;
  const decision = button.classList.contains("approve-button") ? "approve" : "reject";
  button.disabled = true;
  try {
    await request(`${ADOPTIONS_API}/adoptions/${button.dataset.id}/${decision}`, { method: "POST" });
    showMessage(document.querySelector("#adoptionsMessage"), `Solicitud ${decision === "approve" ? "aprobada" : "rechazada"}.`, "success");
    await Promise.all([loadPets(), loadAdoptions()]);
  } catch (error) {
    showMessage(document.querySelector("#adoptionsMessage"), error.message, "error");
    button.disabled = false;
  }
});

loadPets().then(loadAdoptions);
