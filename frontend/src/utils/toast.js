let hideTimer = null;

/** Bottom-right toast, plain DOM (no React tree involved, so it can be called from anywhere). */
export function showToast(message) {
  let el = document.getElementById('app-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'app-toast';
    el.setAttribute('role', 'status');
    el.className = 'no-print surface-card animate-in';
    el.style.cssText = `
      position: fixed; bottom: 28px; right: 28px; z-index: 100;
      max-width: 320px; padding: 14px 20px; display: flex; align-items: flex-start; gap: 10px;
      border-left: 3px solid #9C4A2A; box-shadow: 0 12px 32px rgba(27,36,48,.18);
      font-size: 14px; line-height: 1.4;
    `;
    document.body.appendChild(el);
  }
  el.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9C4A2A" stroke-width="2" style="flex-shrink:0;margin-top:2px">
      <circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4"/>
    </svg>
    <span style="color:#1B2430"></span>
  `;
  el.querySelector('span').textContent = message;
  el.style.display = 'flex';

  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => { el.style.display = 'none'; }, 3000);
}
