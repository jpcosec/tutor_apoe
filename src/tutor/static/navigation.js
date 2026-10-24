// Child views ask the shared workspace to switch tabs without reloading them.
(() => {
  if (window.parent === window) return;
  const views = {'/': 'chat', '/chat': 'chat', '/packages': 'packages', '/graph': 'graph'};
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.download || link.target === '_blank') return;
    const url = new URL(link.href, location.href);
    const view = views[url.pathname];
    if (url.origin !== location.origin || !view || url.hash) return;
    event.preventDefault();
    window.parent.postMessage({type: 'tutor:navigate', view}, location.origin);
  });
})();
