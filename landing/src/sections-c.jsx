// Demo + Architecture + Close + Footer

function Demo() {
  const { t } = useT();
  const rows = [
    { ts: '0:00', script: t('demo.row1.script'), cue: t('demo.row1.cue'), icon: 'file-text' },
    { ts: '0:30', script: t('demo.row2.script'), cue: t('demo.row2.cue'), icon: 'map' },
    { ts: '1:30', script: t('demo.row3.script'), cue: t('demo.row3.cue'), icon: 'link' },
    { ts: '2:00', script: t('demo.row4.script'), cue: t('demo.row4.cue'), icon: 'shield-question' },
    { ts: '3:00', script: t('demo.row5.script'), cue: t('demo.row5.cue'), icon: 'lock' },
    { ts: '3:30', script: t('demo.row6.script'), cue: t('demo.row6.cue'), icon: 'database' },
    { ts: '4:45', script: t('demo.row7.script'), cue: t('demo.row7.cue'), icon: 'circle' },
  ];

  const [ref, shown] = useReveal(0.15);
  return (
    <section id="demo" ref={ref} data-screen-label="07 Demo" className="page-section" style={{ borderTop: '1px solid var(--panel-border)', background: 'linear-gradient(180deg, #0b0f17, #0a0d14)' }}>
      <div className="container">
        <div className={'reveal' + (shown ? ' visible' : '')}>
          <div className="section-label" style={{ marginBottom: 16 }}>{t('demo.label')}</div>
          <h2 className="font-serif" style={{ margin: 0, fontSize: 'clamp(36px, 4.5vw, 56px)', fontWeight: 400, letterSpacing: '-0.015em', maxWidth: '24ch', lineHeight: 1.1 }}>
            {t('demo.h2.a')} <span style={{ fontStyle: 'italic' }}>{t('demo.h2.b')}</span>
          </h2>
        </div>

        <div style={{ marginTop: 72, position: 'relative', maxWidth: 980 }}>
          {/* Vertical timeline */}
          <div style={{
            position: 'absolute', left: 96, top: 0,
            width: 1,
            height: shown ? '100%' : '0%',
            background: 'linear-gradient(180deg, #f59e0b, #1c2433 90%)',
            transition: 'height 1800ms cubic-bezier(0.2,0.7,0.2,1)',
          }} />

          {rows.map((r, i) => (
            <DemoRow key={i} {...r} idx={i} shown={shown} />
          ))}
        </div>
      </div>
    </section>
  );
}

function DemoRow({ ts, script, cue, icon, idx, shown }) {
  return (
    <div className="demo-row" style={{
      display: 'grid',
      gridTemplateColumns: '80px 32px 1fr 1fr',
      alignItems: 'center',
      gap: 16,
      padding: '22px 12px',
      borderBottom: '1px solid var(--panel-border)',
      opacity: shown ? 1 : 0,
      transform: shown ? 'translateY(0)' : 'translateY(12px)',
      transition: `opacity 500ms ease ${idx * 140}ms, transform 500ms ease ${idx * 140}ms, background 240ms ease`,
    }}>
      <div className="font-mono" style={{ fontSize: 13, color: '#f59e0b', letterSpacing: '0.05em' }}>
        [{ts}]
      </div>
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{
          width: 10, height: 10, borderRadius: '50%',
          background: '#0b0f17',
          border: '1.5px solid #f59e0b',
          boxShadow: '0 0 8px rgba(245,158,11,0.5)',
        }} />
      </div>
      <div className="font-serif" style={{ fontSize: 19, color: '#e2e8f0', lineHeight: 1.4, fontStyle: 'italic' }}>
        {script}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: '#94a3b8' }}>
        <span style={{ color: '#22d3ee', flexShrink: 0 }}><Icon name={icon} size={16} /></span>
        <span className="font-mono" style={{ fontSize: 12, letterSpacing: '0.04em' }}>{cue}</span>
      </div>
    </div>
  );
}

// =============================================================
// ARCHITECTURE
// =============================================================
function Architecture() {
  const { t } = useT();
  const [ref, shown] = useReveal(0.25);
  return (
    <section id="architecture" ref={ref} data-screen-label="08 Architecture" className="page-section" style={{ borderTop: '1px solid var(--panel-border)' }}>
      <div className="container">
        <div className={'reveal' + (shown ? ' visible' : '')}>
          <div className="section-label" style={{ marginBottom: 16 }}>{t('arch.label')}</div>
          <h2 className="font-serif" style={{ margin: 0, fontSize: 'clamp(36px, 4.5vw, 56px)', fontWeight: 400, letterSpacing: '-0.015em', maxWidth: '28ch', lineHeight: 1.1 }}>
            {t('arch.h2.a')} <span style={{ fontStyle: 'italic' }}>{t('arch.h2.b')}</span>
          </h2>
        </div>

        <div className="panel-card" style={{ marginTop: 56, padding: '40px 32px', background: '#0a0d14' }}>
          <ArchDiagram shown={shown} />
        </div>

        <p className="font-mono" style={{ marginTop: 24, fontSize: 12, color: '#94a3b8', letterSpacing: '0.05em', textAlign: 'center' }}>
          {t('arch.caption')}
        </p>
      </div>
    </section>
  );
}

function ArchDiagram({ shown }) {
  const { t } = useT();
  const block = (x, y, w, h, label, sub, color = '#1c2433', textColor = '#cbd5e1') => (
    <g>
      <rect x={x} y={y} width={w} height={h} fill="#0f1622" stroke={color} strokeWidth="1" rx="2" />
      <text x={x + w/2} y={y + h/2 - 2} textAnchor="middle" fill={textColor} fontSize="11" fontFamily="JetBrains Mono, monospace" letterSpacing="1">{label}</text>
      {sub && <text x={x + w/2} y={y + h/2 + 12} textAnchor="middle" fill="#475569" fontSize="9" fontFamily="JetBrains Mono, monospace">{sub}</text>}
    </g>
  );

  const colHeader = (x, w, label, color) => (
    <g>
      <text x={x + w/2} y="20" textAnchor="middle" fill={color} fontSize="10" fontFamily="JetBrains Mono, monospace" letterSpacing="3">
        {label}
      </text>
      <line x1={x} y1="30" x2={x + w} y2="30" stroke={color} strokeWidth="0.5" opacity="0.5" />
    </g>
  );

  return (
    <svg viewBox="0 0 980 420" style={{ width: '100%', height: 'auto', display: 'block', opacity: shown ? 1 : 0, transition: 'opacity 800ms ease 200ms' }}>
      {/* Column headers */}
      {colHeader(20, 200, t('arch.col.sense'), '#22d3ee')}
      {colHeader(360, 260, t('arch.col.fuse'), '#f59e0b')}
      {colHeader(760, 200, t('arch.col.surface'), '#10b981')}

      {/* SENSE column — 4 sensors */}
      {block(40, 60, 160, 50, 'SENTINEL-1 SAR', 'satellite radar', '#22d3ee', '#22d3ee')}
      {block(40, 130, 160, 50, 'AISSTREAM', 'maritime AIS', '#22d3ee', '#22d3ee')}
      {block(40, 200, 160, 50, 'GDELT 2.0', 'global news events', '#22d3ee', '#22d3ee')}
      {block(40, 270, 160, 50, 'TELEGRAM', 'public channels', '#22d3ee', '#22d3ee')}

      {/* FUSE+REASON column */}
      {block(380, 60, 220, 50, 'NEO4J', 'knowledge graph', '#f59e0b', '#f59e0b')}
      {block(380, 130, 220, 50, 'DUCKDB', 'fact store', '#f59e0b', '#f59e0b')}

      {/* 5 agents */}
      {block(380, 200, 100, 36, 'GEO', 'agent', '#e879f9', '#e879f9')}
      {block(490, 200, 100, 36, 'OSINT', 'agent', '#e879f9', '#e879f9')}
      {block(380, 246, 100, 36, 'LING', 'agent', '#e879f9', '#e879f9')}
      {block(490, 246, 100, 36, "DEVIL'S A.", 'agent', '#ef4444', '#ef4444')}
      {block(435, 292, 100, 36, 'SUPERVISOR', 'agent', '#e879f9', '#e879f9')}

      {block(380, 348, 220, 36, 'MERKLE LOG', 'tamper-evident', '#10b981', '#10b981')}

      {/* SURFACE column */}
      {block(780, 60, 160, 50, 'BRIEF', 'cited sentences', '#10b981', '#10b981')}
      {block(780, 130, 160, 50, 'MAP', 'maplibre · WebGL', '#10b981', '#10b981')}
      {block(780, 200, 160, 50, 'GRAPH', 'sigma.js', '#10b981', '#10b981')}
      {block(780, 270, 160, 50, 'AUDIT', 'parliament view', '#10b981', '#10b981')}

      {/* Animated dotted dataflow lines */}
      {[60, 130, 200, 270].map((y, i) => (
        <line key={'s' + i} className={shown ? 'arch-line' : ''} x1="200" y1={y + 25} x2="380" y2={130 - i * 0 + (i < 2 ? 60 : 130)} stroke="#22d3ee" strokeWidth="1" opacity="0.7" />
      ))}
      {/* sense -> fuse simplified bus */}
      <path d={`M 200,85 C 280,85 280,85 380,85`} stroke="#22d3ee" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />
      <path d={`M 200,155 C 290,155 290,155 380,155`} stroke="#22d3ee" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />
      <path d={`M 200,225 C 290,225 290,140 380,140`} stroke="#22d3ee" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />
      <path d={`M 200,295 C 290,295 290,90 380,90`} stroke="#22d3ee" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />

      {/* fuse -> agents internal */}
      <line x1="490" y1="180" x2="490" y2="200" stroke="#f59e0b" strokeWidth="1" strokeDasharray="3 3" />
      {/* agents -> merkle */}
      <line x1="485" y1="328" x2="485" y2="348" stroke="#e879f9" strokeWidth="1" strokeDasharray="3 3" />

      {/* fuse -> surface */}
      <path d={`M 600,85 C 680,85 700,85 780,85`} stroke="#10b981" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />
      <path d={`M 600,155 C 680,155 700,155 780,155`} stroke="#10b981" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />
      <path d={`M 600,218 C 680,218 700,225 780,225`} stroke="#10b981" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />
      <path d={`M 600,366 C 680,366 700,295 780,295`} stroke="#10b981" strokeWidth="1.2" fill="none" strokeDasharray="4 6" className={shown ? 'arch-line' : ''} />

      {/* sovereign tag */}
      <text x="490" y="408" textAnchor="middle" fill="#475569" fontSize="9" fontFamily="JetBrains Mono, monospace" letterSpacing="3">
        {t('arch.foot')}
      </text>
    </svg>
  );
}

// =============================================================
// CLOSE
// =============================================================
function Close() {
  const { t } = useT();
  const APP_URL = window.APP_URL || 'http://localhost:5173';
  return (
    <section id="contact" data-screen-label="09 Close" className="page-section" style={{ borderTop: '1px solid var(--panel-border)', textAlign: 'center', padding: '180px 0' }}>
      <div className="container">
        <Reveal>
          <div className="section-label" style={{ marginBottom: 32 }}>{t('close.label')}</div>
        </Reveal>
        <Reveal>
          <p className="font-serif" style={{
            fontSize: 'clamp(32px, 4.4vw, 56px)',
            lineHeight: 1.25,
            margin: 0,
            maxWidth: '26ch',
            marginLeft: 'auto', marginRight: 'auto',
            color: '#e2e8f0',
            fontWeight: 400,
            letterSpacing: '-0.015em',
            textWrap: 'balance',
          }}>
            {t('close.line.a')} <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>{t('close.line.b')}</span>{t('close.line.c')}<span style={{ color: '#f59e0b', fontStyle: 'italic' }}>{t('close.line.d')}</span>
          </p>
        </Reveal>

        <Reveal>
          <div style={{ marginTop: 56, display: 'flex', justifyContent: 'center', gap: 12, flexWrap: 'wrap' }}>
            <Magnetic className="cta-amber" onClick={() => window.location.href = APP_URL}>
              {t('close.cta.enter')}
              <span style={{ marginLeft: 8, display: 'inline-flex', verticalAlign: 'middle' }}><Icon name="arrow-right" size={14} /></span>
            </Magnetic>
            <Magnetic className="cta-ghost" strength={6} onClick={() => window.location.href = 'mailto:contact@damocles.gr?subject=Demo%20Booking'}>
              {t('close.cta.book')}
            </Magnetic>
          </div>
        </Reveal>

        <Reveal>
          <div style={{ marginTop: 40, display: 'flex', justifyContent: 'center', gap: 28, flexWrap: 'wrap' }}>
            <a href="#" className="inline-link" onClick={(e)=>e.preventDefault()}>
              <Icon name="github" size={12} /> &nbsp;GitHub
            </a>
            <a href="#" className="inline-link" onClick={(e)=>e.preventDefault()}>{t('close.link.docs')}</a>
            <a href="#" className="inline-link" onClick={(e)=>e.preventDefault()}>{t('close.link.email')}</a>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// =============================================================
// FOOTER
// =============================================================
function Footer() {
  const { t } = useT();
  return (
    <footer data-screen-label="10 Footer" style={{ borderTop: '1px solid var(--panel-border)', padding: '40px 0 60px' }}>
      <div className="container" style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 24 }}>
        <div className="font-mono" style={{ fontSize: 11, color: '#475569', lineHeight: 1.8, letterSpacing: '0.04em' }}>
          <div>{t('footer.build')}</div>
          <div>{t('footer.sov')}</div>
          <div>{t('footer.lic')}</div>
          <div>{t('footer.eyp')}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <div className="monogram-thread" style={{ height: 22 }} />
            <div className="monogram" />
          </div>
          <div className="sigma-glyph">Σ</div>
        </div>
      </div>
    </footer>
  );
}

window.Demo = Demo;
window.Architecture = Architecture;
window.Close = Close;
window.Footer = Footer;
