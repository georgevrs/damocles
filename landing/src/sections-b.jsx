// Pipeline + Capabilities + Numbers

function Pipeline() {
  const { t } = useT();
  const stages = [
    { num: '01', icon: 'satellite',       title: t('pipe.s1.title'), body: t('pipe.s1.body'), color: '#22d3ee' },
    { num: '02', icon: 'merge',           title: t('pipe.s2.title'), body: t('pipe.s2.body'), color: '#f59e0b' },
    { num: '03', icon: 'brain',           title: t('pipe.s3.title'), body: t('pipe.s3.body'), color: '#e879f9' },
    { num: '04', icon: 'shield-question', title: t('pipe.s4.title'), body: t('pipe.s4.body'), color: '#ef4444' },
    { num: '05', icon: 'lock',            title: t('pipe.s5.title'), body: t('pipe.s5.body'), color: '#10b981' },
  ];
  const [ref, shown] = useReveal(0.25);
  return (
    <section ref={ref} data-screen-label="04 Pipeline" className="page-section" style={{ borderTop: '1px solid var(--panel-border)' }}>
      <div className="container">
        <div className={'reveal' + (shown ? ' visible' : '')}>
          <div className="section-label" style={{ marginBottom: 16 }}>{t('pipe.label')}</div>
          <h2 className="font-serif" style={{ margin: 0, fontSize: 'clamp(36px, 4.5vw, 56px)', fontWeight: 400, letterSpacing: '-0.015em', maxWidth: '24ch', lineHeight: 1.1 }}>
            {t('pipe.h2.a')} <span style={{ fontStyle: 'italic' }}>{t('pipe.h2.b')}</span> {t('pipe.h2.c')}
          </h2>
        </div>

        <div style={{ marginTop: 80, position: 'relative' }}>
          {/* Connecting line */}
          <svg style={{ position: 'absolute', top: 38, left: 0, right: 0, width: '100%', height: 2, zIndex: 0 }} preserveAspectRatio="none" viewBox="0 0 100 2">
            <line
              x1="0" y1="1" x2="100" y2="1"
              stroke="#1c2433" strokeWidth="1"
              pathLength="1"
              strokeDasharray="1"
              strokeDashoffset={shown ? 0 : 1}
              style={{ transition: 'stroke-dashoffset 1800ms cubic-bezier(0.2,0.7,0.2,1) 200ms' }}
            />
          </svg>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, position: 'relative' }}>
            {stages.map((s, i) => (
              <div key={s.num} style={{
                opacity: shown ? 1 : 0,
                transform: shown ? 'translateY(0)' : 'translateY(16px)',
                transition: `opacity 500ms ease ${i * 180}ms, transform 500ms ease ${i * 180}ms`,
              }}>
                {/* Step dot */}
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
                  <div style={{
                    width: 76, height: 76, borderRadius: 4,
                    background: '#0b0f17',
                    border: `1px solid ${s.color}`,
                    boxShadow: `0 0 24px -8px ${s.color}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: s.color,
                    position: 'relative', zIndex: 1,
                  }}>
                    <Icon name={s.icon} size={26} />
                  </div>
                </div>
                <div className="panel-card" style={{ padding: 22, height: 168 }}>
                  <div className="font-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: '#475569', marginBottom: 8 }}>
                    {s.num}
                  </div>
                  <div className="font-serif" style={{ fontSize: 26, color: '#e2e8f0', marginBottom: 10, fontWeight: 500 }}>
                    {s.title}
                  </div>
                  <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.55 }}>
                    {s.body}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// =============================================================
// CAPABILITIES — 2x3 grid with mini visuals
// =============================================================
function Capabilities() {
  const { t } = useT();
  return (
    <section id="capabilities" data-screen-label="05 Capabilities" className="page-section" style={{ borderTop: '1px solid var(--panel-border)', background: 'linear-gradient(180deg, #0a0d14, #0b0f17)' }}>
      <div className="container">
        <Reveal>
          <div className="section-label" style={{ marginBottom: 16 }}>{t('caps.label')}</div>
          <h2 className="font-serif" style={{ margin: 0, fontSize: 'clamp(36px, 4.5vw, 56px)', fontWeight: 400, letterSpacing: '-0.015em', maxWidth: '24ch', lineHeight: 1.1 }}>
            {t('caps.h2.a')} <span style={{ fontStyle: 'italic' }}>{t('caps.h2.b')}</span>
          </h2>
        </Reveal>

        <Reveal stagger threshold={0.15}>
          <div style={{
            marginTop: 64,
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gridAutoRows: 'minmax(280px, auto)',
            gap: 16,
          }}>
            <CapCard span={2} icon="scan"     title={t('caps.c1.title')} body={t('caps.c1.body')} visual={<GreeceVisual />} />
            <CapCard          icon="polygon"  title={t('caps.c2.title')} body={t('caps.c2.body')} visual={<MorphPolygonVisual />} />
            <CapCard          icon="pencil"   title={t('caps.c3.title')} body={t('caps.c3.body')} visual={<DrawCursorVisual />} />
            <CapCard          icon="network"  title={t('caps.c4.title')} body={t('caps.c4.body')} visual={<GraphWiggleVisual />} />
            <CapCard span={2} icon="layers"   title={t('caps.c5.title')} body={t('caps.c5.body')} visual={<LayerStackVisual />} />
            <CapCard span={3} icon="link"     title={t('caps.c6.title')} body={t('caps.c6.body')} visual={<HashChainVisual />} wide />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CapCard({ span = 1, icon, title, body, visual, wide = false }) {
  const { t } = useT();
  return (
    <div className="panel-card" style={{
      gridColumn: `span ${span}`,
      padding: 28,
      display: 'flex',
      flexDirection: wide ? 'row' : 'column',
      gap: wide ? 32 : 0,
      position: 'relative',
      overflow: 'hidden',
    }}>
      <div style={{ flex: wide ? '1 1 50%' : 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#f59e0b', marginBottom: 18 }}>
          <Icon name={icon} size={18} />
          <span className="font-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: '#94a3b8' }}>{t('caps.label.tag')}</span>
        </div>
        <div className="font-serif" style={{ fontSize: 24, color: '#e2e8f0', marginBottom: 12, fontWeight: 500, letterSpacing: '-0.01em', lineHeight: 1.2 }}>
          {title}
        </div>
        <div style={{ fontSize: 14, color: '#94a3b8', lineHeight: 1.6, maxWidth: '42ch' }}>
          {body}
        </div>
      </div>
      <div style={{ flex: wide ? '1 1 50%' : 'auto', marginTop: wide ? 0 : 24, minHeight: wide ? 'auto' : 130, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {visual}
      </div>
    </div>
  );
}

// Real Greek silhouette (mainland + 73 islands) — public-domain Natural Earth.
function GreeceVisual() {
  return (
    <div style={{ width: '100%', maxWidth: 380, position: 'relative' }}>
      <GreeceSilhouette
        width={380} height={220}
        fill="rgba(245, 158, 11, 0.12)"
        stroke="#f59e0b"
        strokeWidth={0.9}
        pulse
      />
      {/* Scan sweep — overlaid bar */}
      <svg viewBox="0 0 380 220" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
        <line x1="0" y1="0" x2="0" y2="220" stroke="#22d3ee" strokeWidth="1" opacity="0.55">
          <animate attributeName="x1" from="0" to="380" dur="4.6s" repeatCount="indefinite" />
          <animate attributeName="x2" from="0" to="380" dur="4.6s" repeatCount="indefinite" />
        </line>
      </svg>
    </div>
  );
}

// AoI inference visual — points clustered around real Lemnos coordinates,
// alpha-shape-style polygon morphing between two plausible cluster hulls.
function MorphPolygonVisual() {
  const { t } = useT();
  // Real Lemnos approach lat/lon points → SVG coords centred around the polygon
  return (
    <svg viewBox="0 0 140 130" style={{ width: 140, height: 130 }}>
      {[[35,55],[55,32],[82,42],[92,68],[58,86],[40,72]].map(([x,y], i) => (
        <circle key={i} cx={x} cy={y} r="2" fill="#f59e0b" />
      ))}
      <polygon points="35,55 55,32 82,42 92,68 58,86 40,72"
               fill="rgba(245,158,11,0.12)" stroke="#f59e0b" strokeWidth="1">
        <animate attributeName="points"
                 values="35,55 55,32 82,42 92,68 58,86 40,72;30,52 58,28 86,40 95,72 52,92 36,75;35,55 55,32 82,42 92,68 58,86 40,72"
                 dur="4s" repeatCount="indefinite" />
      </polygon>
      <text x="65" y="118" textAnchor="middle" fill="#94a3b8" fontSize="8.5" fontFamily="JetBrains Mono, monospace" letterSpacing="1.2">
        {t('caps.aoi.placename')}
      </text>
    </svg>
  );
}

// Analyst-drawn polygon — Naxos coastline used as the actual outline being traced.
// Pulled from window.GREECE_GEOJSON (the polygon containing 25.38 °E, 37.10 °N).
function DrawCursorVisual() {
  const ref = useRef(null);
  const [pathD, vertices] = useMemo(() => {
    const geo = window.GREECE_GEOJSON;
    if (!geo) return ['', []];
    // Find the polygon containing Naxos (25.38, 37.10)
    let target = null;
    for (const poly of geo.coordinates) {
      const ring = poly[0];
      // bbox check
      let lo = Infinity, hi = -Infinity, la = Infinity, ha = -Infinity;
      for (const [x, y] of ring) {
        if (x < lo) lo = x; if (x > hi) hi = x;
        if (y < la) la = y; if (y > ha) ha = y;
      }
      if (25.0 < hi && 25.6 > lo && 36.9 < ha && 37.3 > la) {
        // pick the polygon with the smallest bbox area
        const area = (hi - lo) * (ha - la);
        if (!target || area < target.area) target = { ring, area, lo, hi, la, ha };
      }
    }
    if (!target) return ['', []];
    // Project to 130×130 with 12px padding
    const W = 130, H = 130, pad = 16;
    const lonSpan = (target.hi - target.lo) * Math.cos((target.la + target.ha)/2 * Math.PI/180);
    const latSpan = (target.ha - target.la);
    const scale = Math.min((W - pad*2)/lonSpan, (H - pad*2)/latSpan);
    const drawW = lonSpan * scale, drawH = latSpan * scale;
    const ox = pad + (W - pad*2 - drawW)/2;
    const oy = pad + (H - pad*2 - drawH)/2;
    const cos = Math.cos((target.la + target.ha)/2 * Math.PI/180);
    const project = (lon, lat) => [
      ox + (lon - target.lo) * cos * scale,
      oy + (target.ha - lat) * scale,
    ];
    const pts = target.ring.map(([lon, lat]) => project(lon, lat));
    // Sample every Nth point as a "vertex marker" (max 6)
    const step = Math.max(1, Math.floor(pts.length / 6));
    const verts = pts.filter((_, i) => i % step === 0);
    const d = 'M ' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ') + ' Z';
    return [d, verts];
  }, []);

  return (
    <svg ref={ref} viewBox="0 0 130 130" style={{ width: 130, height: 130 }}>
      {pathD && (
        <path d={pathD}
              fill="rgba(34,211,238,0.10)"
              stroke="#22d3ee"
              strokeWidth="1.2"
              strokeDasharray="3 3"
              strokeLinejoin="round" />
      )}
      <g className="draw-cursor">
        <path d="M 0,0 L 0,12 L 3,9 L 6,15 L 8,14 L 5,8 L 9,8 Z" fill="#22d3ee" />
      </g>
      {vertices.map(([x, y], i) => (
        <rect key={i} x={x-2} y={y-2} width="4" height="4" fill="#22d3ee" />
      ))}
      <text x="65" y="122" textAnchor="middle" fill="#94a3b8" fontSize="8.5" fontFamily="JetBrains Mono, monospace" letterSpacing="1.2">NAXOS</text>
    </svg>
  );
}

function GraphWiggleVisual() {
  const nodes = [[40,60],[70,35],[85,75],[55,90],[100,45],[95,95]];
  const edges = [[0,1],[0,2],[1,2],[2,3],[1,4],[2,5],[4,5]];
  return (
    <svg viewBox="0 0 140 130" style={{ width: 140, height: 130 }}>
      {edges.map(([a,b], i) => (
        <line key={i} x1={nodes[a][0]} y1={nodes[a][1]} x2={nodes[b][0]} y2={nodes[b][1]} stroke="#1c2433" strokeWidth="0.8" />
      ))}
      {nodes.map(([x,y], i) => (
        <g key={i} className="graph-node-wiggle" style={{ animationDelay: (i * 0.4) + 's', transformOrigin: `${x}px ${y}px` }}>
          <circle cx={x} cy={y} r="4" fill="#e879f9" opacity="0.85" />
        </g>
      ))}
    </svg>
  );
}

function LayerStackVisual() {
  return (
    <div className="layer-stack" style={{ position: 'relative', width: 200, height: 130 }}>
      <div className="layer-card l1" style={{ left: 30, top: 50, width: 130, height: 70, background: 'rgba(34,211,238,0.06)', borderColor: 'rgba(34,211,238,0.4)' }}>
        <div className="font-mono" style={{ position: 'absolute', top: 6, left: 8, fontSize: 8, color: '#22d3ee', letterSpacing: '0.15em' }}>VESSELS</div>
      </div>
      <div className="layer-card l2" style={{ left: 30, top: 30, width: 130, height: 70, background: 'rgba(245,158,11,0.06)', borderColor: 'rgba(245,158,11,0.4)' }}>
        <div className="font-mono" style={{ position: 'absolute', top: 6, left: 8, fontSize: 8, color: '#f59e0b', letterSpacing: '0.15em' }}>HEATMAP</div>
      </div>
      <div className="layer-card l3" style={{ left: 30, top: 10, width: 130, height: 70, background: 'rgba(255,255,255,0.04)', borderColor: '#1c2433' }}>
        <div className="font-mono" style={{ position: 'absolute', top: 6, left: 8, fontSize: 8, color: '#94a3b8', letterSpacing: '0.15em' }}>SAR · BASEMAP</div>
        <div style={{ position: 'absolute', inset: 16, background: 'repeating-linear-gradient(45deg, rgba(255,255,255,0.04) 0 1px, transparent 1px 4px)' }} />
      </div>
    </div>
  );
}

function HashChainVisual() {
  const blocks = ['7a3f', 'b91c', 'ddc1', 'f944', '2e1a', '8b07'];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      {blocks.map((b, i) => (
        <React.Fragment key={i}>
          <div className="hash-block" style={{ animation: `hashAppear 400ms ease ${i * 100}ms backwards` }}>
            {b}…
          </div>
          {i < blocks.length - 1 && (
            <div style={{ width: 14, height: 1, background: 'rgba(16,185,129,0.4)' }} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// =============================================================
// NUMBERS
// =============================================================
function Numbers() {
  const { t } = useT();
  const items = [
    { value: 0,    prefix: '€', label: t('numbers.n1'), accent: true },
    { value: 1500, prefix: '€', label: t('numbers.n2') },
    { value: 3,    suffix: t('numbers.n3.suffix'), label: t('numbers.n3') },
    { value: 0,    label: t('numbers.n4'), sub: t('numbers.n4.sub') },
    { value: 5,    label: t('numbers.n5') },
    { value: 41,   label: t('numbers.n6') },
  ];
  return (
    <section data-screen-label="06 Numbers" className="page-section" style={{ borderTop: '1px solid var(--panel-border)' }}>
      <div className="container">
        <Reveal>
          <div className="section-label" style={{ marginBottom: 32 }}>{t('numbers.label')}</div>
        </Reveal>

        <Reveal stagger>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(6, 1fr)',
            gap: 0,
            borderTop: '1px solid var(--panel-border)',
            borderBottom: '1px solid var(--panel-border)',
          }}>
            {items.map((it, i) => (
              <NumberCell key={i} {...it} divider={i > 0} />
            ))}
          </div>
        </Reveal>

        <Reveal>
          <p className="font-serif" style={{ marginTop: 56, fontSize: 24, fontStyle: 'italic', color: '#cbd5e1', maxWidth: '60ch', lineHeight: 1.4 }}>
            {t('numbers.kicker.a')} <span style={{ color: '#f59e0b' }}>{t('numbers.kicker.b')}</span>
          </p>
        </Reveal>
      </div>
    </section>
  );
}

function NumberCell({ value, prefix = '', suffix = '', label, sub, divider, accent }) {
  const [ref, shown] = useReveal(0.4);
  return (
    <div ref={ref} style={{
      padding: '48px 24px',
      borderLeft: divider ? '1px solid var(--panel-border)' : 'none',
      position: 'relative',
    }}>
      <div className="big-number" style={{ color: accent ? '#f59e0b' : '#e2e8f0', marginBottom: 14, fontSize: 'clamp(40px, 4.5vw, 64px)' }}>
        <AnimatedCounter target={value} prefix={prefix} suffix={suffix} />
      </div>
      <div style={{
        height: 2, width: shown ? '100%' : '0%',
        background: 'rgba(245,158,11,0.5)',
        transition: 'width 900ms cubic-bezier(0.2,0.7,0.2,1) 400ms',
        marginBottom: 12,
      }} />
      <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.5 }}>{label}</div>
      {sub && <div className="font-mono" style={{ fontSize: 10, color: '#475569', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

window.Pipeline = Pipeline;
window.Capabilities = Capabilities;
window.Numbers = Numbers;
