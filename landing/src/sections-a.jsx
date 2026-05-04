// Problem section + Citation Chain section

function Problem() {
  const { t } = useT();
  return (
    <section data-screen-label="02 Problem" className="page-section" style={{ borderTop: '1px solid var(--panel-border)' }}>
      <div className="container">
        <Reveal>
          <div className="section-label" style={{ marginBottom: 32 }}>{t('problem.label')}</div>
        </Reveal>

        <Reveal stagger>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 0,
            marginBottom: 80,
            borderTop: '1px solid var(--panel-border)',
            borderBottom: '1px solid var(--panel-border)',
          }}>
            <StatCell value={14000} label={t('problem.stat1')} />
            <StatCell value={47} label={t('problem.stat2')} divider />
            <StatCell value={0.34} decimals={2} suffix="%" label={t('problem.stat3')} divider />
          </div>
        </Reveal>

        <Reveal stagger>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 64, maxWidth: 980 }}>
            <p className="font-serif" style={{ fontSize: 28, lineHeight: 1.35, fontStyle: 'italic', color: '#e2e8f0', margin: 0 }}>
              {t('problem.lead')}
            </p>
            <p style={{ fontSize: 17, lineHeight: 1.7, color: '#94a3b8', margin: 0 }}>
              {t('problem.body')}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function StatCell({ value, label, decimals = 0, suffix = '', divider = false }) {
  return (
    <div style={{
      padding: '56px 32px',
      borderLeft: divider ? '1px solid var(--panel-border)' : 'none',
    }}>
      <div className="big-number" style={{ color: '#f59e0b', marginBottom: 16 }}>
        <AnimatedCounter target={value} decimals={decimals} suffix={suffix} />
      </div>
      <div style={{ fontSize: 14, color: '#94a3b8', lineHeight: 1.5, maxWidth: '32ch' }}>
        {label}
      </div>
    </div>
  );
}

// =============================================================
// CITATION CHAIN — the gold-medal section
// =============================================================
function CitationChain() {
  const { t } = useT();
  const [ref, shown] = useReveal(0.35);
  const [stage, setStage] = useState(0);
  // 0: idle, 1: pulse word, 2: line draws, 3: pin pulses, 4: graph nodes light, 5: edge animates, 6: evidence card up

  useEffect(() => {
    if (!shown) return;
    const seq = [
      [400, 1],   // pulse word
      [600, 2],   // line draws
      [1400, 3],  // pin pulse
      [1800, 4],  // graph nodes
      [2400, 5],  // edge
      [2900, 6],  // evidence card
    ];
    const timers = seq.map(([t, s]) => setTimeout(() => setStage(s), t));
    return () => timers.forEach(clearTimeout);
  }, [shown]);

  return (
    <section ref={ref} data-screen-label="03 Citation Chain" className="page-section" style={{ background: 'linear-gradient(180deg, #0b0f17, #0a0d14)', borderTop: '1px solid var(--panel-border)' }}>
      <div className="container">
        <div className={'reveal' + (shown ? ' visible' : '')}>
          <div className="section-label" style={{ marginBottom: 16 }}>{t('cite.label')}</div>
          <h2 className="font-serif" style={{ margin: 0, fontSize: 'clamp(36px, 4.5vw, 56px)', fontWeight: 400, letterSpacing: '-0.015em', maxWidth: '24ch', lineHeight: 1.1 }}>
            {t('cite.h2.line1')}<br/>
            <span style={{ fontStyle: 'italic', color: '#cbd5e1' }}>{t('cite.h2.line2')}</span>
          </h2>
        </div>

        <div style={{
          marginTop: 72,
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 48,
          alignItems: 'stretch',
          minHeight: 460,
          position: 'relative',
        }}>
          {/* LEFT — fake brief */}
          <div className="panel-card" style={{ padding: 28, position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div className="font-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: '#94a3b8' }}>
                {t('cite.brief.label')}
              </div>
              <div className="font-mono" style={{ fontSize: 10, color: 'var(--audit-emerald)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--audit-emerald)' }} />
                {t('cite.brief.audit')}
              </div>
            </div>

            <div className="font-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: '#f59e0b', marginBottom: 12 }}>{t('cite.brief.bluf')}</div>
            <p className="font-serif" style={{ fontSize: 22, lineHeight: 1.5, color: '#e2e8f0', margin: 0, fontWeight: 400 }}>
              {t('cite.brief.before')}{' '}
              <span
                id="cite-word"
                className={'amber-underline' + (stage >= 2 ? ' drawn' : '')}
                style={{
                  color: '#f59e0b',
                  fontStyle: 'italic',
                  position: 'relative',
                  transition: 'text-shadow 400ms ease',
                  textShadow: stage >= 1 && stage < 4 ? '0 0 16px rgba(245,158,11,0.7)' : 'none',
                }}
              >
                {t('cite.brief.cited')}
              </span>{' '}
              {t('cite.brief.after')}
            </p>

            <div style={{ marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--panel-border)' }}>
              <div className="font-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: '#94a3b8', marginBottom: 10 }}>{t('cite.brief.sources')}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <SourceRow icon="satellite" label={t('cite.brief.src1')} id="ddc1f9" />
                <SourceRow icon="globe" label={t('cite.brief.src2')} id="a47b03" />
                <SourceRow icon="message" label={t('cite.brief.src3')} id="9f2e1a" />
              </div>
            </div>

            <div style={{ position: 'absolute', bottom: 16, left: 28, right: 28, display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#475569', fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.1em' }}>
              <span>{t('cite.brief.foot1')}</span>
              <span>{t('cite.brief.foot2')}</span>
            </div>
          </div>

          {/* RIGHT — map + graph */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Map strip — REAL Lemnos quadrant from public-domain Greek geometry */}
            <div className="panel-card" style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#07090e' }}>
              <div className="font-mono" style={{ position: 'absolute', top: 14, left: 16, fontSize: 10, letterSpacing: '0.2em', color: '#94a3b8', zIndex: 2 }}>
                {t('cite.map.label')}
              </div>
              <div className="font-mono" style={{ position: 'absolute', top: 14, right: 16, fontSize: 10, color: '#475569', zIndex: 2 }}>
                {t('cite.map.coord')}
              </div>

              <GeoQuadrant
                width={400} height={240}
                bbox={[24.4, 39.0, 26.8, 40.6]}   // Lemnos · Lesvos · Imbros approach
                fill="#0f1622" stroke="#1c2433"
              >
                {(project) => {
                  // Project the cited incident point and the citation source-word origin
                  const [pinX, pinY] = project(25.31, 39.94);   // north of Lemnos
                  const [v1X, v1Y]   = project(25.36, 39.98);   // dark vessel A
                  const [v2X, v2Y]   = project(25.42, 39.99);   // dark vessel B
                  return (
                    <g>
                      {/* Vessel ghost trails leading into the loitering zone */}
                      <path d={`M 60,200 Q ${pinX-80},${pinY+30} ${pinX-10},${pinY-2}`} stroke="rgba(245,158,11,0.20)" strokeWidth="1" fill="none" strokeDasharray="2 3" />
                      <path d={`M 90,210 Q ${pinX-60},${pinY+50} ${pinX-2},${pinY+4}`} stroke="rgba(245,158,11,0.20)" strokeWidth="1" fill="none" strokeDasharray="2 3" />

                      {/* Path from cited brief sentence (off-canvas left) to the pin */}
                      <path
                        d={`M -40,-80 Q ${pinX-160},${pinY-40} ${pinX},${pinY}`}
                        stroke="#f59e0b" strokeWidth="1.4" fill="none"
                        strokeDasharray="500"
                        strokeDashoffset={stage >= 2 ? 0 : 500}
                        style={{ transition: 'stroke-dashoffset 1200ms cubic-bezier(0.2,0.7,0.2,1)' }}
                      />

                      {/* Pin + pulse rings */}
                      <g transform={`translate(${pinX}, ${pinY})`}>
                        {stage >= 3 && (
                          <>
                            <circle r="8" fill="none" stroke="#f59e0b" strokeWidth="1"
                                    style={{ transformOrigin: 'center', animation: 'citePulse 1.6s ease-out infinite' }} />
                            <circle r="14" fill="none" stroke="#f59e0b" strokeWidth="1"
                                    style={{ transformOrigin: 'center', animation: 'citePulse 1.6s ease-out infinite 0.4s' }} />
                          </>
                        )}
                        <circle r="4" fill="#f59e0b" />
                        <circle r="2" fill="#fff" opacity="0.8" />
                      </g>

                      {/* Vessel positions — small cyan rectangles */}
                      <g transform={`translate(${v1X}, ${v1Y})`}>
                        <rect x="-3" y="-1" width="6" height="2" fill="#22d3ee" opacity="0.85" />
                      </g>
                      <g transform={`translate(${v2X}, ${v2Y})`}>
                        <rect x="-3" y="-1" width="6" height="2" fill="#22d3ee" opacity="0.85" />
                      </g>

                      {/* Lemnos label */}
                      <text x={pinX-2} y={pinY+50} textAnchor="middle" fill="#475569" fontSize="9" fontFamily="JetBrains Mono, monospace" letterSpacing="1.5">LEMNOS</text>
                    </g>
                  );
                }}
              </GeoQuadrant>
            </div>

            {/* Graph strip */}
            <div className="panel-card" style={{ height: 160, position: 'relative', overflow: 'hidden' }}>
              <div className="font-mono" style={{ position: 'absolute', top: 14, left: 16, fontSize: 10, letterSpacing: '0.2em', color: '#94a3b8' }}>
                {t('cite.graph.label')}
              </div>
              <div className="font-mono" style={{ position: 'absolute', top: 14, right: 16, fontSize: 10, color: '#475569' }}>
                {t('cite.graph.count')}
              </div>
              <svg viewBox="0 0 400 160" style={{ width: '100%', height: '100%', display: 'block' }}>
                {/* faint background nodes */}
                {[[60,80],[80,40],[110,110],[330,40],[360,90],[340,130],[180,140],[260,30],[290,100]].map(([x,y], i) => (
                  <circle key={i} cx={x} cy={y} r="2" fill="#1c2433" />
                ))}
                {/* faint edges */}
                <line x1="60" y1="80" x2="180" y2="140" stroke="#1c2433" strokeWidth="0.5" />
                <line x1="330" y1="40" x2="360" y2="90" stroke="#1c2433" strokeWidth="0.5" />

                {/* Three highlighted nodes */}
                <GraphNode cx="140" cy="80" label="Vessel-A" lit={stage >= 4} delay={0} />
                <GraphNode cx="220" cy="60" label="Sighting" lit={stage >= 4} delay={200} type="sight" />
                <GraphNode cx="300" cy="90" label="Telegram" lit={stage >= 4} delay={400} type="msg" />

                {/* CITES edges */}
                <CitesEdge x1="140" y1="80" x2="220" y2="60" active={stage >= 5} delay={0} />
                <CitesEdge x1="220" y1="60" x2="300" y2="90" active={stage >= 5} delay={300} />
              </svg>
            </div>
          </div>

          {/* Evidence card slides up */}
          <div style={{
            position: 'absolute',
            left: 'calc(50% - 180px)',
            bottom: stage >= 6 ? -30 : -260,
            width: 360,
            transition: 'bottom 700ms cubic-bezier(0.2,0.7,0.2,1), opacity 600ms ease',
            opacity: stage >= 6 ? 1 : 0,
            zIndex: 5,
          }}>
            <div className="panel-card" style={{ padding: 16, background: '#0c121d', boxShadow: '0 -20px 60px -10px rgba(0,0,0,0.6), 0 0 0 1px rgba(245,158,11,0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div className="font-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: '#f59e0b' }}>
                  {t('cite.evidence.label')}
                </div>
                <div className="font-mono" style={{ fontSize: 10, color: '#94a3b8' }}>
                  {t('cite.evidence.id')}
                </div>
              </div>
              <div className="sar-tile" style={{ height: 130, position: 'relative' }}>
                {/* Bounding rect overlay */}
                <div style={{ position: 'absolute', top: 38, left: 110, width: 56, height: 28, border: '1.5px solid #f59e0b', boxShadow: '0 0 12px rgba(245,158,11,0.5)' }}>
                  <div className="font-mono" style={{ position: 'absolute', top: -16, left: 0, fontSize: 9, color: '#f59e0b', letterSpacing: '0.1em' }}>VES-A · 12.4m</div>
                </div>
                <div style={{ position: 'absolute', top: 70, left: 178, width: 48, height: 24, border: '1.5px solid #f59e0b', boxShadow: '0 0 12px rgba(245,158,11,0.5)' }}>
                  <div className="font-mono" style={{ position: 'absolute', top: -16, left: 0, fontSize: 9, color: '#f59e0b', letterSpacing: '0.1em' }}>VES-B · 11.1m</div>
                </div>
              </div>
              <div className="font-mono" style={{ marginTop: 10, fontSize: 10, color: '#94a3b8', display: 'flex', justifyContent: 'space-between' }}>
                <span>{t('cite.evidence.hash')}</span>
                <span style={{ color: 'var(--audit-emerald)' }}>{t('cite.evidence.ok')}</span>
              </div>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 64, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 64, alignItems: 'start' }}>
          <p className="font-serif" style={{ fontSize: 32, lineHeight: 1.25, fontStyle: 'italic', color: '#f59e0b', margin: 0 }}>
            {t('cite.kicker')[0]}<br/>{t('cite.kicker')[1]}
          </p>
          <p style={{ fontSize: 16, lineHeight: 1.7, color: '#94a3b8', margin: 0 }}>
            {t('cite.body')}
          </p>
        </div>
      </div>
    </section>
  );
}

function SourceRow({ icon, label, id }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--panel-border)', borderRadius: 2 }}>
      <span style={{ color: '#f59e0b' }}><Icon name={icon} size={14} /></span>
      <span style={{ fontSize: 12, color: '#cbd5e1', flex: 1 }}>{label}</span>
      <span className="font-mono" style={{ fontSize: 10, color: '#475569' }}>#{id}</span>
    </div>
  );
}

function GraphNode({ cx, cy, label, lit, delay, type = 'vessel' }) {
  const fill = lit ? '#f59e0b' : '#1c2433';
  const stroke = lit ? '#f59e0b' : '#334155';
  return (
    <g style={{ transition: `all 400ms ease ${delay}ms` }}>
      {lit && <circle cx={cx} cy={cy} r="14" fill="rgba(245,158,11,0.15)" />}
      <circle cx={cx} cy={cy} r="7" fill={fill} stroke={stroke} strokeWidth="1.5" style={{ transition: `all 400ms ease ${delay}ms` }} />
      <text x={cx} y={cy + 22} textAnchor="middle" fill={lit ? '#e2e8f0' : '#475569'} fontSize="9" fontFamily="JetBrains Mono, monospace" style={{ transition: `fill 400ms ease ${delay}ms`, letterSpacing: '0.05em' }}>
        {label}
      </text>
    </g>
  );
}

function CitesEdge({ x1, y1, x2, y2, active, delay }) {
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.hypot(dx, dy);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  return (
    <g>
      <line
        x1={x1} y1={y1} x2={x2} y2={y2}
        stroke="#f59e0b" strokeWidth="1.2"
        strokeDasharray={len}
        strokeDashoffset={active ? 0 : len}
        style={{ transition: `stroke-dashoffset 600ms cubic-bezier(0.2,0.7,0.2,1) ${delay}ms` }}
      />
      {active && (
        <text x={mx} y={my - 5} fill="#f59e0b" fontSize="8" fontFamily="JetBrains Mono, monospace" textAnchor="middle" style={{ opacity: active ? 1 : 0, transition: `opacity 300ms ease ${delay + 400}ms`, letterSpacing: '0.15em' }}>
          CITES
        </text>
      )}
    </g>
  );
}

window.Problem = Problem;
window.CitationChain = CitationChain;
