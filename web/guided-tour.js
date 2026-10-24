/* A non-modal walkthrough. Highlights real controls and never runs their actions. */
(() => {
  class GuidedTour {
    constructor({onClose = () => {}} = {}) {
      this.onClose = onClose;
      this.active = false;
      this.index = 0;
      this.disposers = [];
      this.keyHandler = event => { if (event.key === 'Escape' && this.active && !event.target?.ownerDocument?.querySelector('dialog[open]')) { event.preventDefault(); this.close(); } };
    }
    start(steps) {
      this.close(false);
      this.steps = steps;
      this.active = true;
      this.returnFocus = document.activeElement;
      this.layer = document.createElement('div');
      this.layer.className = 'guide-layer';
      this.layer.innerHTML = `<div class="guide-ring" aria-hidden="true"></div><section class="guide-card" role="dialog" aria-modal="false" aria-labelledby="guide-title" aria-describedby="guide-text"><div class="guide-head"><span class="guide-count"></span><button class="guide-close" aria-label="Salir del recorrido">×</button></div><h2 id="guide-title"></h2><p id="guide-text"></p><p class="guide-hint" role="status" aria-live="polite"></p><div class="guide-actions"><button class="guide-back">Atrás</button><button class="guide-next">Siguiente →</button></div><small>Puedes usar la zona resaltada. Esc para salir.</small></section>`;
      document.body.append(this.layer);
      this.ring = this.layer.querySelector('.guide-ring');
      this.card = this.layer.querySelector('.guide-card');
      this.back = this.layer.querySelector('.guide-back');
      this.next = this.layer.querySelector('.guide-next');
      this.layer.querySelector('.guide-close').onclick = () => this.close();
      this.back.onclick = () => this.show(this.index - 1);
      this.next.onclick = () => { if (this.next.disabled) return; if (this.index === this.steps.length - 1) this.close(); else this.show(this.index + 1); };
      const windows = [window, ...[...document.querySelectorAll('iframe')].map(frame => frame.contentWindow)];
      for (const target of windows) {
        target.addEventListener('keydown', this.keyHandler, true);
        this.disposers.push(() => target.removeEventListener('keydown', this.keyHandler, true));
      }
      this.timer = setInterval(() => this.tick(), 180);
      this.show(0);
    }
    show(index) {
      if (!this.active || index < 0 || index >= this.steps.length) return;
      this.index = index;
      const step = this.steps[index];
      step.prepare?.();
      this.wasReady = step.ready ? Boolean(step.ready()) : true;
      this.layer.querySelector('.guide-count').textContent = `RECORRIDO · ${index + 1} DE ${this.steps.length}`;
      this.layer.querySelector('#guide-title').textContent = step.title;
      this.layer.querySelector('#guide-text').textContent = step.text;
      this.next.textContent = index === this.steps.length - 1 ? 'Terminar ✓' : 'Siguiente →';
      this.back.disabled = index === 0;
      const target = step.target();
      target?.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
      this.tick();
      this.layer.querySelector('.guide-close').focus({preventScroll:true});
    }
    tick() {
      if (!this.active) return;
      const step = this.steps[this.index];
      const ready = !step.ready || Boolean(step.ready());
      const working = Boolean(step.busy?.());
      this.next.disabled = !ready || working;
      this.layer.querySelector('.guide-hint').textContent = working ? 'La operación sigue en curso. Espera; avanzaremos al terminar.' : !ready ? step.wait || 'Completa la acción indicada para continuar.' : 'Puedes continuar cuando quieras.';
      if (step.auto && ready && !this.wasReady && !working) {
        this.show(Math.min(this.index + 1, this.steps.length - 1));
        return;
      }
      const target = step.target();
      const readingSource = Boolean(target?.ownerDocument.querySelector('dialog[open]'));
      this.layer.style.visibility = readingSource ? 'hidden' : '';
      if (readingSource) return;
      const rect = target && this.rectangle(target);
      if (!rect || rect.width < 1 || rect.height < 1) {
        this.ring.hidden = true;
        this.card.style.left = Math.max(12, window.innerWidth - this.card.offsetWidth - 20) + 'px';
        this.card.style.top = Math.max(12, window.innerHeight - this.card.offsetHeight - 20) + 'px';
        return;
      }
      this.ring.hidden = false;
      Object.assign(this.ring.style, {left:rect.left-5+'px', top:rect.top-5+'px', width:rect.width+10+'px', height:rect.height+10+'px'});
      const width = this.card.offsetWidth, height = this.card.offsetHeight, gap = 17;
      let x = rect.right + gap, y = rect.top;
      if (x + width > window.innerWidth - 12) {
        x = Math.min(rect.left, window.innerWidth-width-16);
        y = rect.bottom + gap;
        if (y + height > window.innerHeight - 12) y = rect.top-height-gap;
        if (y < 12) { y = window.innerHeight-height-16; x = rect.left-width-gap; }
      }
      this.card.style.left = Math.max(12, Math.min(x, window.innerWidth-width-12)) + 'px';
      this.card.style.top = Math.max(12, Math.min(y, window.innerHeight-height-12)) + 'px';
    }
    rectangle(target) {
      const raw = target.getBoundingClientRect();
      let rect = {left:raw.left, top:raw.top, right:raw.right, bottom:raw.bottom};
      let docWindow = target.ownerDocument.defaultView;
      while (docWindow !== window) {
        const frame = docWindow.frameElement;
        if (!frame) return null;
        const frameRect = frame.getBoundingClientRect();
        rect = {left:Math.max(rect.left,0)+frameRect.left, top:Math.max(rect.top,0)+frameRect.top,
                right:Math.min(rect.right,docWindow.innerWidth)+frameRect.left,
                bottom:Math.min(rect.bottom,docWindow.innerHeight)+frameRect.top};
        docWindow = frame.ownerDocument.defaultView;
      }
      rect.left = Math.max(0,rect.left); rect.top = Math.max(0,rect.top);
      rect.right = Math.min(window.innerWidth,rect.right); rect.bottom = Math.min(window.innerHeight,rect.bottom);
      return {...rect,width:rect.right-rect.left,height:rect.bottom-rect.top};
    }
    close(restore = true) {
      if (!this.active) return;
      this.active = false;
      clearInterval(this.timer);
      this.disposers.splice(0).forEach(dispose => dispose());
      this.layer.remove();
      if (restore && this.returnFocus?.isConnected) this.returnFocus.focus({preventScroll:true});
      this.onClose();
    }
  }
  window.GuidedTour = GuidedTour;
})();
