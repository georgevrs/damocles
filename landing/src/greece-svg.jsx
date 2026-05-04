// Greece-shape components driven by REAL public-domain geometry.
//
// `window.GREECE_GEOJSON` is a MultiPolygon (mainland + 73 islands).
// `window.GREECE_CARD_GEOJSON` is the same outline, more aggressively
// simplified for small-icon use (727 points instead of 1891).
// Both files are auto-generated from datasets/geo-countries (PD source).

// Convert a MultiPolygon ring into a single SVG-path d attribute.
// Coordinates are lon,lat in degrees; the caller passes a projector.
function ringsToPath(geo, project) {
  const polys = geo?.coordinates ?? [];
  const segs = [];
  for (const poly of polys) {
    const ring = poly[0];
    if (!ring || ring.length < 3) continue;
    const pts = ring.map(([lon, lat]) => project(lon, lat));
    segs.push(
      'M ' + pts.map(([x, y]) => x.toFixed(2) + ',' + y.toFixed(2)).join(' L ') + ' Z'
    );
  }
  return segs.join(' ');
}

// Equirectangular projector with cos(latMid) correction.
function makeProjector(geo, viewW, viewH, padding = 6) {
  const polys = geo?.coordinates ?? [];
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  for (const poly of polys) {
    for (const [lon, lat] of poly[0]) {
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
  }
  const midLat = (minLat + maxLat) / 2;
  const cos = Math.cos(midLat * Math.PI / 180);
  const lonSpan = (maxLon - minLon) * cos;
  const latSpan = (maxLat - minLat);
  const availW = viewW - padding * 2;
  const availH = viewH - padding * 2;
  const scale = Math.min(availW / lonSpan, availH / latSpan);
  const drawW = lonSpan * scale;
  const drawH = latSpan * scale;
  const ox = padding + (availW - drawW) / 2;
  const oy = padding + (availH - drawH) / 2;
  return (lon, lat) => [
    ox + (lon - minLon) * cos * scale,
    oy + (maxLat - lat) * scale,
  ];
}

// Real Greek silhouette — drop-in replacement for the old hand-drawn one.
function GreeceSilhouette({
  width = 320,
  height = 200,
  fill = 'rgba(245, 158, 11, 0.15)',
  stroke = '#f59e0b',
  strokeWidth = 1,
  className = '',
  pulse = true,
  geo = null,
}) {
  const g = geo || window.GREECE_CARD_GEOJSON || window.GREECE_GEOJSON;
  if (!g) return null;
  const project = useMemo(() => makeProjector(g, width, height), [g, width, height]);
  const d = useMemo(() => ringsToPath(g, project), [g, project]);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}
         style={{ display: 'block', overflow: 'visible' }}
         className={className}>
      <g className={pulse ? 'greece-pulse' : ''}>
        <path d={d} fill={fill} stroke={stroke} strokeWidth={strokeWidth} strokeLinejoin="round" />
      </g>
    </svg>
  );
}

// Find a single named polygon by an inside-test against a sample point. Used
// for the Lemnos-quadrant zoom in the citation chain section.
function pickPolygonByPoint(geo, lon, lat) {
  if (!geo) return null;
  for (const poly of geo.coordinates) {
    const ring = poly[0];
    if (pointInRing(lon, lat, ring)) return [ring];
  }
  return null;
}
function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    const intersect = ((yi > y) !== (yj > y)) &&
      (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

// Render a real geographic quadrant (lon range × lat range) — used by the
// citation chain "Lemnos quadrant" map strip and reused for any zoom-in card.
function GeoQuadrant({
  width = 400, height = 240,
  bbox,                       // [minLon, minLat, maxLon, maxLat]
  fill = '#0f1622', stroke = '#1c2433',
  className = '',
  children = null,
}) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const midLat = (minLat + maxLat) / 2;
  const cos = Math.cos(midLat * Math.PI / 180);
  const lonSpan = (maxLon - minLon) * cos;
  const latSpan = (maxLat - minLat);
  const scale = Math.min(width / lonSpan, height / latSpan);
  const drawW = lonSpan * scale;
  const drawH = latSpan * scale;
  const ox = (width - drawW) / 2;
  const oy = (height - drawH) / 2;
  const project = (lon, lat) => [
    ox + (lon - minLon) * cos * scale,
    oy + (maxLat - lat) * scale,
  ];

  // Clip every Greek polygon's outer ring against the bbox. We only render
  // polygons whose bbox intersects the view bbox — keeps the path short.
  const polys = (window.GREECE_GEOJSON?.coordinates ?? []);
  const segs = [];
  for (const poly of polys) {
    const ring = poly[0];
    if (!ring) continue;
    let lo = Infinity, hi = -Infinity, la = Infinity, ha = -Infinity;
    for (const [x, y] of ring) {
      if (x < lo) lo = x; if (x > hi) hi = x;
      if (y < la) la = y; if (y > ha) ha = y;
    }
    // bbox-vs-bbox reject
    if (hi < minLon || lo > maxLon || ha < minLat || la > maxLat) continue;
    const pts = ring.map(([lon, lat]) => project(lon, lat));
    segs.push('M ' + pts.map(([x, y]) => x.toFixed(2) + ',' + y.toFixed(2)).join(' L ') + ' Z');
  }
  const d = segs.join(' ');

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={className}
         style={{ width: '100%', height: '100%', display: 'block' }}>
      {/* lon/lat reference grid */}
      {Array.from({ length: Math.floor(maxLat) - Math.ceil(minLat) + 1 }, (_, i) => {
        const lat = Math.ceil(minLat) + i;
        const [, py] = project(minLon, lat);
        return <line key={'la'+i} x1="0" y1={py} x2={width} y2={py} stroke="#1c2433" strokeWidth="0.5" />;
      })}
      {Array.from({ length: Math.floor(maxLon) - Math.ceil(minLon) + 1 }, (_, i) => {
        const lon = Math.ceil(minLon) + i;
        const [px] = project(lon, minLat);
        return <line key={'lo'+i} x1={px} y1="0" x2={px} y2={height} stroke="#1c2433" strokeWidth="0.5" />;
      })}
      <path d={d} fill={fill} stroke={stroke} strokeWidth="0.8" strokeLinejoin="round" />
      {typeof children === 'function' ? children(project) : children}
    </svg>
  );
}

window.GreeceSilhouette = GreeceSilhouette;
window.GeoQuadrant = GeoQuadrant;
window.makeProjector = makeProjector;
window.ringsToPath = ringsToPath;
