// Selección de silla. Solo marca la silla elegida y llena el formulario de "Continuar".
// La reserva se confirma en la página siguiente (/events/<id>/confirm), que genera Flask.

const seatIdInput = document.getElementById("selected-seat-id");
const continueButton = document.getElementById("continue-button");
const bottomBarSeat = document.getElementById("bottom-bar-seat");
const selectionSection = document.getElementById("selection-section");
const selectionRow = document.getElementById("selection-row");
const selectionNumber = document.getElementById("selection-number");

let selectedSeat = null;

document.querySelectorAll(".seat-map .seat.available").forEach(function (seatButton) {
  seatButton.addEventListener("click", function () {
    if (selectedSeat !== null) {
      selectedSeat.classList.remove("selected");
    }
    selectedSeat = seatButton;
    selectedSeat.classList.add("selected");

    // La zona y la fila están en el div de la fila; el número, dentro del botón
    const row = seatButton.closest(".seat-row");
    const section = row.dataset.section;
    const rowName = row.dataset.row;
    const number = seatButton.querySelector(".seat-number").textContent;

    selectionSection.textContent = section;
    selectionRow.textContent = rowName;
    selectionNumber.textContent = number;
    bottomBarSeat.textContent = section + " · Fila " + rowName + " · Silla " + number;

    seatIdInput.value = seatButton.dataset.seatId;
    continueButton.disabled = false;
  });
});
