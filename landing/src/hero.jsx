// Hero — animated Aegean map (canvas-drawn, no maplibre needed)
//
// Geometry is REAL: Greek sovereign territory + western Turkish coastline,
// loaded from window.GREECE_GEOJSON / window.TURKEY_WEST_GEOJSON
// (auto-generated from public-domain Natural-Earth-derived data, simplified
// to ~1.1km Douglas-Peucker tolerance — see landing/src/geo-greece.jsx).
//
// We project lon/lat directly to canvas coordinates with a small slow-pan
// drift to keep the scene alive without scrolling the actual viewport.

function AegeanCanvas() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let raf;
    let w, h, dpr;

    const landColor = '#0f1622';
    const landStroke = 'rgba(245, 158, 11, 0.18)';   // hairline amber so coastlines read

    // View window — slightly wider than Greek bbox so the western Turkish coast
    // shows up on the right edge.
    const VIEW_LON_MIN = 19.0,  VIEW_LON_MAX = 30.0;
    const VIEW_LAT_MIN = 34.5,  VIEW_LAT_MAX = 42.0;

    // Pull all polygons (including Turkey-west) into a single flat array of
    // ring arrays so the draw loop is just iteration.
    const greecePolys = (window.GREECE_GEOJSON?.coordinates || []);
    const turkeyPolys = (window.TURKEY_WEST_GEOJSON?.coordinates || []);
    // Each entry in coordinates is [outerRing, ...holes]; we only render outer.
    const greeceRings = greecePolys.map(p => p[0]).filter(r => r && r.length >= 3);
    const turkeyRings = turkeyPolys.map(p => p[0]).filter(r => r && r.length >= 3);

    // Trails as real lon/lat — Aegean shipping lanes between named ports.
    const trails = [
      // Lemnos -> Lesvos -> Chios
      { pts: [[25.27, 39.92], [26.55, 39.10], [26.13, 38.37]], prog: 0,    speed: 0.0018, hue: 'amber' },
      // Piraeus -> Heraklion (Crete)
      { pts: [[23.62, 37.94], [24.60, 36.80], [25.13, 35.34]], prog: 0.30, speed: 0.0014, hue: 'cyan' },
      // Rhodes -> Karpathos -> Crete
      { pts: [[28.22, 36.43], [27.22, 35.51], [25.13, 35.34]], prog: 0.60, speed: 0.0012, hue: 'amber' },
      // Piraeus -> Naxos
      { pts: [[23.62, 37.94], [24.95, 37.10], [25.38, 37.10]], prog: 0.10, speed: 0.0016, hue: 'cyan' },
      // Chios -> Lesvos -> Lemnos
      { pts: [[26.13, 38.37], [26.55, 39.10], [25.27, 39.92]], prog: 0.40, speed: 0.0015, hue: 'amber' },
      // Crete (east) -> Rhodes
      { pts: [[26.10, 35.20], [27.22, 35.78], [28.22, 36.43]], prog: 0.20, speed: 0.0011, hue: 'cyan' },
      // Thessaloniki -> Lemnos
      { pts: [[22.94, 40.64], [24.50, 40.30], [25.27, 39.92]], prog: 0.70, speed: 0.0017, hue: 'amber' },
      // Corfu -> Patras -> Kalamata
      { pts: [[19.92, 39.62], [21.74, 38.25], [22.11, 37.04]], prog: 0.50, speed: 0.0013, hue: 'cyan' },
      // Cyclades patrol (Paros · Naxos · Mykonos · Tinos)
      { pts: [[25.15, 37.08], [25.38, 37.10], [25.37, 37.45], [25.16, 37.55], [25.15, 37.08]], prog: 0.0, speed: 0.0010, hue: 'amber' },
      // Anatolian coast (Cesme region → Bodrum)
      { pts: [[26.30, 38.32], [27.05, 37.50], [27.43, 36.96]], prog: 0.55, speed: 0.0014, hue: 'cyan' },
    ];

    // Incidents at real Aegean coordinates.
    const incidents = [
      { lon: 25.30, lat: 39.85 }, // North Aegean / Lemnos approach
      { lon: 25.20, lat: 37.15 }, // Cyclades
      { lon: 27.80, lat: 36.50 }, // SE Aegean / Kos-Rhodes
    ];
    const incidentStart = performance.now();

    let bearing = 0;
    let driftLon = 0, driftLat = 0;

    const resize = () => {
      dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      const rect = canvas.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);

    // ── Real lon/lat → canvas projection ────────────────────────────────
    // Equirectangular with a latitude-correction so Greek territory looks
    // proportional (cos of mid-latitude). Aspect-ratio-aware: if the canvas
    // is wider/taller than the view ratio we fit-to-contain to keep the map
    // from squishing.
    const project = () => {
      const midLat = (VIEW_LAT_MIN + VIEW_LAT_MAX) / 2;
      const cos = Math.cos(midLat * Math.PI / 180);
      const lonSpan = (VIEW_LON_MAX - VIEW_LON_MIN);
      const latSpan = (VIEW_LAT_MAX - VIEW_LAT_MIN);
      const viewAR = (lonSpan * cos) / latSpan;        // map AR
      const canvasAR = w / h;
      let scale, ox = 0, oy = 0;
      if (canvasAR > viewAR) {
        // canvas wider than map — pad horizontally
        scale = h / latSpan;
        const drawW = lonSpan * cos * scale;
        ox = (w - drawW) / 2;
      } else {
        scale = (w / cos) / lonSpan;
        const drawH = latSpan * scale;
        oy = (h - drawH) / 2;
      }
      return { scale, cos, ox, oy };
    };

    const mapX = (lon) => {
      const { scale, cos, ox } = project();
      return ox + (lon - VIEW_LON_MIN + driftLon) * cos * scale;
    };
    const mapY = (lat) => {
      const { scale, oy } = project();
      // y grows downward; latitude grows northward → invert
      return oy + (VIEW_LAT_MAX - lat + driftLat) * scale;
    };

    const drawRing = (ring) => {
      ctx.beginPath();
      for (let i = 0; i < ring.length; i++) {
        const px = mapX(ring[i][0]), py = mapY(ring[i][1]);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.closePath();
    };

    // polyline length / point-at in lon/lat space (equirectangular is fine for short legs)
    const polylineLen = (pts) => {
      let len = 0;
      for (let i = 1; i < pts.length; i++) {
        const dx = (pts[i][0] - pts[i-1][0]);
        const dy = (pts[i][1] - pts[i-1][1]);
        len += Math.hypot(dx, dy);
      }
      return len;
    };
    const pointAt = (pts, t) => {
      const total = polylineLen(pts);
      let target = t * total;
      for (let i = 1; i < pts.length; i++) {
        const dx = pts[i][0] - pts[i-1][0];
        const dy = pts[i][1] - pts[i-1][1];
        const seg = Math.hypot(dx, dy);
        if (target <= seg) {
          const k = target / seg;
          return [pts[i-1][0] + dx * k, pts[i-1][1] + dy * k];
        }
        target -= seg;
      }
      return pts[pts.length - 1];
    };

    const tick = (now) => {
      bearing += 0.05;
      // Slow drift across both axes — a fraction of a degree, sub-pixel mostly
      driftLon = Math.sin(bearing * 0.004) * 0.06;
      driftLat = Math.cos(bearing * 0.005) * 0.04;

      // Background — deep aegean night
      ctx.fillStyle = '#0a0d14';
      ctx.fillRect(0, 0, w, h);

      // Latitude/longitude reference grid (real degrees)
      ctx.strokeStyle = 'rgba(28, 36, 51, 0.55)';
      ctx.lineWidth = 1;
      for (let lat = Math.ceil(VIEW_LAT_MIN); lat <= Math.floor(VIEW_LAT_MAX); lat++) {
        const py = mapY(lat);
        ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(w, py); ctx.stroke();
      }
      for (let lon = Math.ceil(VIEW_LON_MIN); lon <= Math.floor(VIEW_LON_MAX); lon++) {
        const px = mapX(lon);
        ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, h); ctx.stroke();
      }

      // Land — every Greek polygon (mainland + 73 islands) + western Turkey
      ctx.fillStyle = landColor;
      ctx.strokeStyle = landStroke;
      ctx.lineWidth = 0.8;
      for (const ring of greeceRings) { drawRing(ring); ctx.fill(); ctx.stroke(); }
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.10)';   // Turkey: not the protagonist
      for (const ring of turkeyRings) { drawRing(ring); ctx.fill(); ctx.stroke(); }

      // Vessel trails
      trails.forEach((t) => {
        t.prog = (t.prog + t.speed) % 1;
        // Draw the full polyline faint
        ctx.beginPath();
        t.pts.forEach((p, i) => {
          const x = mapX(p[0]), y = mapY(p[1]);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.strokeStyle = t.hue === 'amber' ? 'rgba(245, 158, 11, 0.12)' : 'rgba(34, 211, 238, 0.10)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Glowing trailing dot — also draw a short bright trail
        const trailLen = 60;
        for (let i = 0; i < trailLen; i++) {
          const tt = t.prog - (i / trailLen) * 0.18;
          if (tt < 0) continue;
          const [nx, ny] = pointAt(t.pts, tt);
          const alpha = (1 - i / trailLen) * (t.hue === 'amber' ? 0.7 : 0.55);
          ctx.fillStyle = t.hue === 'amber'
            ? `rgba(245, 158, 11, ${alpha})`
            : `rgba(34, 211, 238, ${alpha})`;
          ctx.beginPath();
          ctx.arc(mapX(nx), mapY(ny), 1.6 - i * 0.018, 0, Math.PI * 2);
          ctx.fill();
        }
        // Lead dot glow
        const [hx, hy] = pointAt(t.pts, t.prog);
        const grad = ctx.createRadialGradient(mapX(hx), mapY(hy), 0, mapX(hx), mapY(hy), 14);
        if (t.hue === 'amber') {
          grad.addColorStop(0, 'rgba(245, 158, 11, 0.7)');
          grad.addColorStop(1, 'rgba(245, 158, 11, 0)');
        } else {
          grad.addColorStop(0, 'rgba(34, 211, 238, 0.55)');
          grad.addColorStop(1, 'rgba(34, 211, 238, 0)');
        }
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(mapX(hx), mapY(hy), 14, 0, Math.PI * 2);
        ctx.fill();
      });

      // Incidents — pulse rings at real lon/lat
      const elapsed = now - incidentStart;
      incidents.forEach((p, i) => {
        const phase = ((elapsed / 2400) + i * 0.33) % 1;
        const radius = 6 + phase * 38;
        const alpha = 0.9 * (1 - phase);
        const px = mapX(p.lon), py = mapY(p.lat);
        ctx.strokeStyle = `rgba(245, 158, 11, ${alpha})`;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(px, py, radius, 0, Math.PI * 2);
        ctx.stroke();
        // center
        ctx.fillStyle = '#f59e0b';
        ctx.beginPath();
        ctx.arc(px, py, 3.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.6)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(px, py, 6, 0, Math.PI * 2);
        ctx.stroke();
      });

      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }}
    />
  );
}

// Operational-app URL. Configurable at deploy time via window.DAMOCLES_APP_URL;
// defaults to the Vite dev port the operational frontend uses (5173).
const APP_URL = (typeof window !== 'undefined' && window.DAMOCLES_APP_URL) || 'http://localhost:5173';
window.APP_URL = APP_URL;

function HeroHeadline() {
  const { t, lang } = useT();
  const ref = useRef(null);
  useEffect(() => {
    const words = ref.current.querySelectorAll('.word-reveal');
    words.forEach((w, i) => {
      // Re-trigger on language switch — strip "in", reapply with stagger
      w.classList.remove('in');
      setTimeout(() => w.classList.add('in'), 80 + i * 70);
    });
  }, [lang]);
  const line1 = t('hero.h1.line1').split(/\s+/).filter(Boolean);
  const line2 = t('hero.h1.line2').split(/\s+/).filter(Boolean);
  return (
    <h1 ref={ref} className="font-serif hero-shadow" style={{
      margin: 0,
      fontWeight: 400,
      fontSize: 'clamp(48px, 7.4vw, 104px)',
      lineHeight: 1.02,
      letterSpacing: '-0.02em',
      color: '#f5f7fa',
      maxWidth: '15ch',
    }}>
      <span style={{ display: 'block' }}>
        {line1.map((w, i) => (
          <span key={lang + i} className="word-reveal" style={{ marginRight: '0.25em' }}>{w}</span>
        ))}
      </span>
      <span style={{ display: 'block', fontStyle: 'italic', color: '#e2e8f0' }}>
        {line2.map((w, i) => (
          <span key={lang + i} className="word-reveal" style={{ marginRight: '0.25em' }}>{w}</span>
        ))}
      </span>
    </h1>
  );
}

function Hero() {
  const { t } = useT();
  const heroRef = useRef(null);
  const textWrapRef = useRef(null);
  // cursor parallax
  useEffect(() => {
    const hero = heroRef.current;
    if (!hero) return;
    let raf;
    const onMove = (e) => {
      const r = hero.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        if (textWrapRef.current) {
          textWrapRef.current.style.transform = `translate(${x * -6}px, ${y * -6}px)`;
        }
      });
    };
    const onLeave = () => {
      if (textWrapRef.current) textWrapRef.current.style.transform = '';
    };
    hero.addEventListener('mousemove', onMove);
    hero.addEventListener('mouseleave', onLeave);
    return () => {
      hero.removeEventListener('mousemove', onMove);
      hero.removeEventListener('mouseleave', onLeave);
      cancelAnimationFrame(raf);
    };
  }, []);

  const smoothTo = (id) => (e) => {
    e.preventDefault();
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <section ref={heroRef} data-screen-label="01 Hero" style={{
      height: '100vh',
      minHeight: 720,
      position: 'relative',
      overflow: 'hidden',
      background: '#0a0d14',
    }}>
      <div className="hide-mobile" style={{ position: 'absolute', inset: 0 }}>
        <AegeanCanvas />
      </div>
      {/* Static SVG fallback for mobile would go here */}

      {/* Darkening overlays */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse at 30% 50%, rgba(11,15,23,0.55), rgba(11,15,23,0.85) 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(180deg, rgba(11,15,23,0.6) 0%, rgba(11,15,23,0) 25%, rgba(11,15,23,0) 70%, rgba(11,15,23,0.85) 100%)',
        pointerEvents: 'none',
      }} />

      <div ref={textWrapRef} className="parallax-wrap" style={{
        position: 'relative',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '0 clamp(24px, 6vw, 96px)',
        zIndex: 2,
      }}>
        <div className="section-label hero-shadow" style={{ marginBottom: 28, color: '#f59e0b' }}>
          <span style={{ display: 'inline-block', width: 6, height: 6, background: '#f59e0b', borderRadius: '50%', marginRight: 10, boxShadow: '0 0 8px #f59e0b' }} />
          {t('hero.eyebrow')}
        </div>

        <HeroHeadline />

        <p className="hero-shadow" style={{
          marginTop: 32,
          maxWidth: '54ch',
          fontSize: 17,
          lineHeight: 1.6,
          color: '#94a3b8',
          fontWeight: 300,
        }}>
          {t('hero.subhead')}
        </p>

        <div style={{ marginTop: 40, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Magnetic className="cta-amber" onClick={() => { window.location.href = APP_URL; }}>
            {t('hero.cta.enter')}
            <span style={{ marginLeft: 8, display: 'inline-flex', verticalAlign: 'middle' }}><Icon name="arrow-right" size={14} /></span>
          </Magnetic>
          <Magnetic className="cta-ghost" strength={6} onClick={smoothTo('demo')}>
            {t('hero.cta.demo')}
          </Magnetic>
          <Magnetic className="cta-ghost" strength={6} onClick={smoothTo('architecture')}>
            {t('hero.cta.arch')}
          </Magnetic>
        </div>

        <div className="font-mono" style={{ marginTop: 56, display: 'flex', gap: 24, color: '#475569', fontSize: 11, letterSpacing: '0.12em' }}>
          {t('hero.sources').map((s, i) => (<span key={i}>{s}</span>))}
        </div>
      </div>

      {/* Scroll cue */}
      <div className="chevron-bounce hide-mobile" style={{
        position: 'absolute',
        bottom: 32,
        left: '50%',
        transform: 'translateX(-50%)',
        color: '#94a3b8',
        zIndex: 3,
        textAlign: 'center',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        letterSpacing: '0.18em',
      }}>
        {t('hero.scroll')}
        <div style={{ marginTop: 6 }}><Icon name="chevron-down" size={16} /></div>
      </div>

      {/* Live indicator */}
      <div className="font-mono" style={{
        position: 'absolute', top: '50%', right: 32, transform: 'translateY(-50%) rotate(90deg)',
        transformOrigin: 'right center',
        fontSize: 10, color: '#475569', letterSpacing: '0.3em',
        zIndex: 3,
      }}>
        {t('hero.live')}
      </div>
    </section>
  );
}

function Topbar() {
  const { t } = useT();
  const smoothTo = (id) => (e) => {
    e.preventDefault();
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  return (
    <div className="topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div className="monogram-thread" style={{ height: 10 }} />
          <div className="monogram" />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 0 }}>
          <span className="font-mono" style={{ fontSize: 13, letterSpacing: '0.2em', color: '#e2e8f0' }}>DAMOCLES</span>
          <span className="version-chip">v1.2 · phase 2</span>
        </div>
      </div>
      <div className="hide-mobile" style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
        <a href="#capabilities" onClick={smoothTo('capabilities')}>{t('topbar.capabilities')}</a>
        <a href="#architecture" onClick={smoothTo('architecture')}>{t('topbar.architecture')}</a>
        <a href="#demo" onClick={smoothTo('demo')}>{t('topbar.demo')}</a>
        <a href="#contact" onClick={smoothTo('contact')}>{t('topbar.contact')}</a>
        <LangSwitch />
        <a
          href={APP_URL}
          style={{
            background: '#f59e0b',
            color: '#0b0f17',
            padding: '8px 14px',
            borderRadius: 2,
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            letterSpacing: '0.1em',
            fontWeight: 600,
            textDecoration: 'none',
            border: '1px solid #f59e0b',
            transition: 'box-shadow 200ms ease',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 0 24px -4px rgba(245,158,11,0.6)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.boxShadow = ''; }}
        >
          {t('topbar.enter')}
          <Icon name="arrow-right" size={12} stroke="#0b0f17" />
        </a>
      </div>
    </div>
  );
}

window.Hero = Hero;
window.Topbar = Topbar;
