export function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
export function replayAnimation(element, className = "motion-enter") {
    if (!element || prefersReducedMotion())
        return;
    element.classList.remove(className);
    void element.offsetWidth;
    element.classList.add(className);
}
export function staggerChildren(container, itemSelector, className = "motion-stagger-item") {
    if (!container || prefersReducedMotion())
        return;
    const items = container.querySelectorAll(itemSelector);
    items.forEach((item, index) => {
        item.classList.remove(className);
        item.style.animationDelay = "";
        void item.offsetWidth;
        item.classList.add(className);
        item.style.animationDelay = `${Math.min(index, 10) * 40}ms`;
    });
}
