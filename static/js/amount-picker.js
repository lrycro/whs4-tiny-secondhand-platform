// Reusable "amount field" behavior: preset buttons fill the input, an inline
// X button clears it, manual typing still works normally. Driven entirely by
// markup (.amount-field / [data-amount-clear] / [data-amount-value]) so it can
// be dropped into any form without page-specific JS.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".amount-field").forEach(function (field) {
    var input = field.querySelector("input");
    var clearBtn = field.querySelector("[data-amount-clear]");
    var presetBtns = field.querySelectorAll("[data-amount-value]");

    if (!input || !clearBtn) return;

    function updateClearVisibility() {
      clearBtn.classList.toggle("is-visible", input.value.length > 0);
    }

    presetBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        input.value = btn.getAttribute("data-amount-value");
        updateClearVisibility();
        input.focus();
      });
    });

    clearBtn.addEventListener("click", function () {
      input.value = "";
      updateClearVisibility();
      input.focus();
    });

    input.addEventListener("input", updateClearVisibility);
    updateClearVisibility();
  });
});
