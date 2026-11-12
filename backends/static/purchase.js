// Compra de sillas sin recargar la página: llama a la API con fetch y muestra el resultado.

const form = document.getElementById("purchase-form");
const selectedSeatText = document.getElementById("selected-seat");
const message = document.getElementById("purchase-message");
const availableCount = document.getElementById("available-count");
const eventId = form.dataset.eventId;

let selectedSeat = null;

function showMessage(text, type) {
  message.textContent = text;
  message.className = "message " + type;
}

function markAsSold(seatButton) {
  seatButton.classList.remove("available", "selected");
  seatButton.classList.add("sold");
  seatButton.disabled = true;
  selectedSeat = null;
  selectedSeatText.textContent = "Elige una silla libre en el mapa.";
}

// Al hacer clic en una silla libre, queda elegida
document.querySelectorAll(".seat-map .seat.available").forEach(function (seatButton) {
  seatButton.addEventListener("click", function () {
    if (selectedSeat !== null) {
      selectedSeat.classList.remove("selected");
    }
    selectedSeat = seatButton;
    selectedSeat.classList.add("selected");
    selectedSeatText.textContent = "Silla elegida: " + seatButton.dataset.label;
  });
});

form.addEventListener("submit", async function (event) {
  event.preventDefault();

  if (selectedSeat === null) {
    showMessage("Primero elige una silla libre en el mapa.", "error");
    return;
  }

  const seatButton = selectedSeat;
  const url = "/api/events/" + eventId + "/seats/" + seatButton.dataset.seatId + "/purchase";
  const buyer = {
    buyer_name: form.elements.buyer_name.value,
    buyer_email: form.elements.buyer_email.value,
  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buyer),
    });
    const result = await response.json();

    if (response.status === 201) {
      showMessage("Compraste la silla " + seatButton.dataset.label + ".", "success");
      markAsSold(seatButton);
      availableCount.textContent = Number(availableCount.textContent) - 1;
    } else if (response.status === 409) {
      showMessage("Esa silla ya fue vendida. Elige otra.", "error");
      markAsSold(seatButton);
    } else {
      // 400, 404 o 503: la API explica el problema en "message"
      showMessage(result.message, "error");
    }
  } catch (error) {
    showMessage("No se pudo comunicar con el servidor. Intenta de nuevo.", "error");
  }
});
