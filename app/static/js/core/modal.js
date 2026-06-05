const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const stack = [];

function dialogRoot(modalEl) {
  return modalEl.querySelector(".contact-notes-dialog, .jobs-panel-dialog, .lead-detail-dialog") || modalEl;
}

function focusables(modalEl) {
  return [...dialogRoot(modalEl).querySelectorAll(FOCUSABLE)].filter(
    (el) => !el.closest(".hidden") && el.offsetParent !== null,
  );
}

export function isModalOpen(modalEl) {
  return modalEl && !modalEl.classList.contains("hidden");
}

export function openModal(modalEl, { initialFocus } = {}) {
  if (!modalEl || isModalOpen(modalEl)) return;
  const previous = document.activeElement;
  modalEl.classList.remove("hidden");
  modalEl.setAttribute("aria-modal", "true");
  const entry = { modalEl, previous };
  stack.push(entry);
  const target =
    (initialFocus && dialogRoot(modalEl).querySelector(initialFocus)) ||
    focusables(modalEl)[0] ||
    dialogRoot(modalEl);
  requestAnimationFrame(() => target?.focus?.());
}

export function closeModal(modalEl) {
  if (!modalEl) return;
  modalEl.classList.add("hidden");
  modalEl.removeAttribute("aria-modal");
  const index = stack.findIndex((item) => item.modalEl === modalEl);
  if (index >= 0) {
    const [entry] = stack.splice(index, 1);
    entry.previous?.focus?.();
  }
}

export function handleModalKeydown(event) {
  const entry = stack[stack.length - 1];
  if (!entry || !isModalOpen(entry.modalEl)) return;

  if (event.key === "Escape") {
    event.preventDefault();
    const { modalEl } = entry;
    modalEl.dispatchEvent(new CustomEvent("modal:escape", { bubbles: true }));
    if (isModalOpen(modalEl)) closeModal(modalEl);
    return;
  }

  if (event.key !== "Tab") return;
  const items = focusables(entry.modalEl);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
