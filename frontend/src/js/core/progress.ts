/** Update progress bar fills via transform (avoids width layout thrash). */
export function setProgressFill(el, percent) {
  if (!el) return;
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  el.style.transform = `scaleX(${value / 100})`;
}

export function resetProgressFill(el) {
  if (!el) return;
  el.style.transform = "scaleX(0)";
}
