// ===== Hooks =====
const { useEffect, useRef, useState, useMemo, useCallback } = React;

function useReveal(threshold = 0.3) {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      });
    }, { threshold });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [threshold]);
  return [ref, shown];
}

// AnimatedCounter
function AnimatedCounter({ target, duration = 1400, decimals = 0, suffix = '', prefix = '' }) {
  const [ref, shown] = useReveal(0.4);
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!shown) return;
    let raf;
    const start = performance.now();
    const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4);
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = easeOutQuart(t);
      setVal(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [shown, target, duration]);

  const formatted = decimals > 0
    ? val.toFixed(decimals)
    : Math.floor(val).toLocaleString('fr-FR').replace(/\u00a0/g, '\u202f'); // thin space
  return <span ref={ref} className="font-serif">{prefix}{formatted}{suffix}</span>;
}

// Magnetic button wrapper
function Magnetic({ children, strength = 8, className = '', ...rest }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf;
    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.hypot(dx, dy);
      if (dist < 80) {
        const f = (1 - dist / 80) * strength;
        const tx = (dx / 80) * strength;
        const ty = (dy / 80) * strength;
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          el.style.transform = `translate(${tx}px, ${ty}px)`;
        });
      } else {
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          el.style.transform = '';
        });
      }
    };
    const onLeave = () => {
      cancelAnimationFrame(raf);
      el.style.transform = '';
    };
    window.addEventListener('mousemove', onMove);
    el.addEventListener('mouseleave', onLeave);
    return () => {
      window.removeEventListener('mousemove', onMove);
      el.removeEventListener('mouseleave', onLeave);
      cancelAnimationFrame(raf);
    };
  }, [strength]);
  return <button ref={ref} className={className} {...rest}>{children}</button>;
}

// Reveal wrapper
function Reveal({ children, stagger = false, className = '', threshold = 0.2 }) {
  const [ref, shown] = useReveal(threshold);
  const cls = (stagger ? 'reveal-stagger' : 'reveal') + (shown ? ' visible' : '') + (className ? ' ' + className : '');
  return <div ref={ref} className={cls}>{children}</div>;
}

// Tiny inline icons (Lucide-style stroked SVGs)
const Icon = ({ name, size = 18, className = '', stroke = 'currentColor' }) => {
  const props = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke, strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', className };
  switch (name) {
    case 'satellite': return <svg {...props}><path d="M5 5l4 4"/><path d="M2 13a10 10 0 0 0 9 9"/><path d="M2 19a4 4 0 0 0 4 4"/><path d="M11.41 11.41L7.59 15.23a2 2 0 1 1-2.83-2.83l3.83-3.83"/><path d="M15.41 7.41L19.23 3.59a2 2 0 1 1 2.83 2.83l-3.83 3.83"/><path d="M11 11l3 3"/></svg>;
    case 'merge': return <svg {...props}><path d="M8 6v6"/><path d="M8 18v0"/><path d="M16 6v0"/><path d="M16 12c0 6-8 6-8 12"/><circle cx="8" cy="3" r="1.5"/><circle cx="16" cy="3" r="1.5"/><circle cx="8" cy="21" r="1.5"/></svg>;
    case 'brain': return <svg {...props}><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44A2.5 2.5 0 0 1 4 17.5a2.5 2.5 0 0 1-2-2.45A2.5 2.5 0 0 1 4 11a2.5 2.5 0 0 1 0-4.5A2.5 2.5 0 0 1 7 4.5 2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2a2.5 2.5 0 0 0-2.5 2.5v15a2.5 2.5 0 0 0 4.96.44A2.5 2.5 0 0 0 20 17.5a2.5 2.5 0 0 0 2-2.45A2.5 2.5 0 0 0 20 11a2.5 2.5 0 0 0 0-4.5A2.5 2.5 0 0 0 17 4.5 2.5 2.5 0 0 0 14.5 2Z"/></svg>;
    case 'shield-question': return <svg {...props}><path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8z"/><path d="M9.1 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>;
    case 'lock': return <svg {...props}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>;
    case 'map': return <svg {...props}><path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z"/><path d="M9 3v15"/><path d="M15 6v15"/></svg>;
    case 'scan': return <svg {...props}><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/></svg>;
    case 'polygon': return <svg {...props}><path d="M5 4l14 3-2 13L7 20 4 11z"/></svg>;
    case 'pencil': return <svg {...props}><path d="M21.17 6.83 17.17 2.83a2 2 0 0 0-2.83 0L3 14.17V21h6.83L21.17 9.66a2 2 0 0 0 0-2.83z"/><path d="m15 5 4 4"/></svg>;
    case 'network': return <svg {...props}><circle cx="12" cy="12" r="2"/><circle cx="5" cy="5" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="m6.5 6.5 4 4"/><path d="m17.5 6.5-4 4"/><path d="m6.5 17.5 4-4"/><path d="m17.5 17.5-4-4"/></svg>;
    case 'layers': return <svg {...props}><path d="m12 2 9 5-9 5-9-5 9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/></svg>;
    case 'link': return <svg {...props}><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.72-1.71"/></svg>;
    case 'arrow-right': return <svg {...props}><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>;
    case 'chevron-down': return <svg {...props}><path d="m6 9 6 6 6-6"/></svg>;
    case 'play': return <svg {...props}><polygon points="6 3 20 12 6 21 6 3"/></svg>;
    case 'file-text': return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>;
    case 'database': return <svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></svg>;
    case 'github': return <svg {...props}><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>;
    case 'circle': return <svg {...props}><circle cx="12" cy="12" r="10"/></svg>;
    case 'eye': return <svg {...props}><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>;
    case 'message': return <svg {...props}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>;
    case 'globe': return <svg {...props}><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>;
    default: return null;
  }
};

window.useReveal = useReveal;
window.AnimatedCounter = AnimatedCounter;
window.Magnetic = Magnetic;
window.Reveal = Reveal;
window.Icon = Icon;
