// Compra de una silla sin recargar la página: llama a la API con fetch y muestra el resultado.

const form = document.getElementById("purchase-form");
const buyButton = document.getElementById("buy-button");
const summaryEmpty = document.getElementById("summary-empty");
const message = document.getElementById("purchase-message");
const availableCount = document.getElementById("available-count");
const buyBarSeat = document.getElementById("buy-bar-seat");
const selectionSection = document.getElementById("selection-section");
const selectionRow = document.getElementById("selection-row");
const selectionNumber = document.getElementById("selection-number");
const eventId = form.dataset.eventId;

let selectedSeat = null;

// La sección y la fila están en el div de la fila; el número, dentro del botón
function seatInfo(seatButton) {
  const row = seatButton.closest(".seat-row");
  return {
    section: row.dataset.section,
    row: row.dataset.row,
    number: seatButton.querySelector(".seat-number").textContent,
  };
}

function seatLabel(seatButton) {
  const info = seatInfo(seatButton);
  return info.section + ", fila " + info.row + ", silla " + info.number;
}

// Resalta el paso actual en la barra de pasos (2 Sillas o 3 Confirmación)
function setCurrentStep(stepNumber) {
  document.querySelectorAll(".step").forEach(function (step) {
    step.classList.toggle("current", step.dataset.step === String(stepNumber));
  });
}

function showMessage(text, type) {
  message.textContent = text;
  message.className = "message " + type;
}

// El botón Comprar solo se habilita con una silla elegida y el nombre y el correo llenos
function updateBuyButton() {
  const name = form.elements.buyer_name.value.trim();
  const email = form.elements.buyer_email.value.trim();
  buyButton.disabled = selectedSeat === null || name === "" || email === "";
}

// Actualiza las tarjetas TU SELECCIÓN y RESUMEN y la barra de abajo
function showSelection() {
  if (selectedSeat === null) {
    selectionSection.textContent = "—";
    selectionRow.textContent = "—";
    selectionNumber.textContent = "—";
    buyBarSeat.textContent = "Ninguna";
    form.hidden = true;
    summaryEmpty.hidden = false;
  } else {
    const info = seatInfo(selectedSeat);
    selectionSection.textContent = info.section;
    selectionRow.textContent = info.row;
    selectionNumber.textContent = info.number;
    buyBarSeat.textContent = seatLabel(selectedSeat);
    form.hidden = false;
    summaryEmpty.hidden = true;
  }
  updateBuyButton();
}

function markAsSold(seatButton) {
  seatButton.classList.remove("available", "selected");
  seatButton.classList.add("sold");
  seatButton.disabled = true;
  selectedSeat = null;
  showSelection();
}

// Al hacer clic en una silla libre, queda seleccionada (solo una a la vez)
document.querySelectorAll(".seat-map .seat.available").forEach(function (seatButton) {
  seatButton.addEventListener("click", function () {
    if (selectedSeat !== null) {
      selectedSeat.classList.remove("selected");
    }
    selectedSeat = seatButton;
    selectedSeat.classList.add("selected");
    setCurrentStep(2);
    showMessage("", "");
    showSelection();
  });
});

form.elements.buyer_name.addEventListener("input", updateBuyButton);
form.elements.buyer_email.addEventListener("input", updateBuyButton);

form.addEventListener("submit", async function (event) {
  event.preventDefault();
  if (selectedSeat === null) {
    return;
  }

  const seatButton = selectedSeat;
  const url = "/api/events/" + eventId + "/seats/" + seatButton.dataset.seatId + "/purchase";
  const buyer = {
    buyer_name: form.elements.buyer_name.value,
    buyer_email: form.elements.buyer_email.value,
  };

  // Evita enviar la misma compra dos veces mientras llega la respuesta
  buyButton.disabled = true;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buyer),
    });
    const result = await response.json();

    if (response.status === 201) {
      showMessage("Compraste la silla " + seatLabel(seatButton) + ".", "success");
      markAsSold(seatButton);
      availableCount.textContent = Number(availableCount.textContent) - 1;
      setCurrentStep(3);
    } else if (response.status === 409) {
      showMessage("Esa silla ya fue vendida. Elige otra.", "error");
      markAsSold(seatButton);
    } else {
      // 400, 404 o 503: la API explica el problema en "message"
      showMessage(result.message, "error");
      updateBuyButton();
    }
  } catch (error) {
    showMessage("No se pudo comunicar con el servidor. Intenta de nuevo.", "error");
    updateBuyButton();
  }
});
