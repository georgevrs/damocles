// i18n — landing page bilingual (EN ↔ EL).
//
// The dictionary keys are deliberately verbose & hierarchical so missing
// keys are obvious in code review. Greek copy is drafted to match the
// register of the demo script (instrument, not brochure — see PLAN.md
// "Phrases to lean on" / "Phrases to avoid").

const I18N = {
  en: {
    'topbar.capabilities': 'Capabilities',
    'topbar.architecture': 'Architecture',
    'topbar.demo':         'Demo',
    'topbar.contact':      'Contact',
    'topbar.enter':        'Enter the platform',
    'topbar.lang':         'EL',

    'hero.eyebrow':        'EYP · NATIONAL SECURITY INNOVATION CHALLENGE 2026',
    'hero.h1.line1':       'Cited intelligence,',
    'hero.h1.line2':       'at the speed of the threat.',
    'hero.subhead':        'Sovereign analysis platform fusing SAR, AIS, GDELT and Telegram into a Merkle-chained knowledge graph. Built in Greek, in three weeks, for €1,500.',
    'hero.cta.demo':       'Watch the demo',
    'hero.cta.arch':       'Read the architecture',
    'hero.cta.enter':      'Enter the platform',
    'hero.scroll':         'SCROLL',
    'hero.live':           'LIVE · AEGEAN 25.5°E 37.5°N',
    'hero.sources':        ['SAR · SENTINEL-1', 'AIS · AISSTREAM', 'GDELT 2.0', 'TELEGRAM'],

    'problem.label':       '§ 02 · THE PROBLEM',
    'problem.stat1':       "signals waiting in an analyst's queue today",
    'problem.stat2':       'that they will review by end of shift',
    'problem.stat3':       'the coverage rate',
    'problem.lead':        'Intelligence today is a triage problem disguised as an information problem.',
    'problem.body':        'Damocles changes that number — by routing every signal through a transparent agent layer that surfaces only what is corroborated, cited, and challenged.',

    'cite.label':          '§ 03 · THE CITATION CHAIN',
    'cite.h2.line1':       'Not a summary of a summary.',
    'cite.h2.line2':       'A citation chain — the same standard you would expect in a court.',
    'cite.brief.label':    'BRIEF · 04.MAY.2026 · 06:14 EEST',
    'cite.brief.audit':    'AUDIT-CHAIN OK',
    'cite.brief.bluf':     'BLUF',
    'cite.brief.before':   'Two unflagged vessels have been',
    'cite.brief.cited':    'loitering north of Lemnos',
    'cite.brief.after':    'for 38 hours, with AIS transponders dark since 23:11.',
    'cite.brief.sources':  'SOURCES · 3',
    'cite.brief.src1':     'Sentinel-1 SAR · 04.05.26 04:42Z',
    'cite.brief.src2':     'AISStream · transponder gap 38h12m',
    'cite.brief.src3':     'Telegram · @aegean-watch · 02:18',
    'cite.brief.foot1':    'SUPERVISOR: confirmed',
    'cite.brief.foot2':    "DEVIL'S ADV: no rebuttal",
    'cite.map.label':      'MAP · LEMNOS QUADRANT',
    'cite.map.coord':      '39.94°N · 25.31°E',
    'cite.graph.label':    'KNOWLEDGE GRAPH',
    'cite.graph.count':    '3 / 12,408 NODES',
    'cite.evidence.label': 'EVIDENCE · SAR TILE',
    'cite.evidence.id':    'S1A_IW_GRDH · 04.05.26 04:42Z',
    'cite.evidence.hash':  'SHA-256: ddc1f9...',
    'cite.evidence.ok':    'VERIFIED',
    'cite.kicker':         ['One click. Three sources.', 'Zero hallucinations.'],
    'cite.body':           'Every sentence in every brief traces to a node in the knowledge graph. Click a sentence, the map flies to the source coordinates, the graph highlights the cited node, and the raw evidence — SAR tile, news article, or Telegram message — opens beside the brief.',

    'pipe.label':          '§ 04 · THE PIPELINE',
    'pipe.h2.a':           'From signal to',
    'pipe.h2.b':           'signed brief',
    'pipe.h2.c':           'in five steps.',
    'pipe.s1.title':       'Sense',
    'pipe.s1.body':        'Sentinel-1 SAR · AIS · GDELT · Telegram',
    'pipe.s2.title':       'Fuse',
    'pipe.s2.body':        'Spatiotemporal correlation, threat-grade rules',
    'pipe.s3.title':       'Reason',
    'pipe.s3.body':        '5 LLM agents in parallel',
    'pipe.s4.title':       'Challenge',
    'pipe.s4.body':        "Devil's Advocate adversarial review",
    'pipe.s5.title':       'Sign',
    'pipe.s5.body':        'Merkle-chained audit log',

    'caps.label':          '§ 05 · PHASE 2 · OPERATIONAL',
    'caps.h2.a':           'Six capabilities that',
    'caps.h2.b':           'institutionalize skepticism.',
    'caps.label.tag':      'CAPABILITY',
    'caps.c1.title':       'Greece-wide standing coverage',
    'caps.c1.body':        'A daily 7-day scan persisting to a DuckDB fact store. No per-watch re-fetch. The country is observed continuously, not on request.',
    'caps.c2.title':       'AI-defined Areas of Interest',
    'caps.c2.body':        'HDBSCAN density clustering and alpha-shape concavity, named in Greek by an LLM with cited reasoning.',
    'caps.c3.title':       'Analyst-drawn polygons',
    'caps.c3.body':        'terra-draw on MapLibre. Every operator-defined region becomes a first-class citizen of the knowledge graph.',
    'caps.c4.title':       'WebGL knowledge graph',
    'caps.c4.body':        'Sigma.js renderer scaling past ten thousand nodes without a frame drop. The graph is the interface.',
    'caps.c5.title':       'Rich layered map',
    'caps.c5.body':        'Vessel trajectories, semantic icons, satellite basemap toggle, news density heatmap. Every layer toggleable, every layer cited.',
    'caps.c6.title':       'Tamper-evident audit chain',
    'caps.c6.body':        'Every model call, every analyst action, hashed and Merkle-chained across two stores. Any parliamentary committee can verify the log has not been tampered with — on the chain. Always.',
    'caps.aoi.placename':  'NORTH AEGEAN',

    'numbers.label':       '§ 06 · THE NUMBERS',
    'numbers.n1':          'to run',
    'numbers.n2':          'total hardware',
    'numbers.n3.suffix':   ' weeks',
    'numbers.n3':          'build time',
    'numbers.n4':          'Greek bytes leaving Greek infrastructure',
    'numbers.n4.sub':      '(production)',
    'numbers.n5':          'agents in the reasoning layer',
    'numbers.n6':          'audit-chain entries verified pre-pitch',
    'numbers.kicker.a':    "These are the numbers we can't change. They are also the numbers",
    'numbers.kicker.b':    'Palantir cannot match.',

    'demo.label':          '§ 07 · HOW THE DEMO LANDS',
    'demo.h2.a':           'Five minutes.',
    'demo.h2.b':           'Seven beats.',
    'demo.row1.script':    '"Open the brief. Read the BLUF."',
    'demo.row1.cue':       'Brief panel — BLUF visible',
    'demo.row2.script':    '"Click the underlined claim. Watch the map fly."',
    'demo.row2.cue':       'Map flies to Lemnos quadrant',
    'demo.row3.script':    '"Three sources. Each one verifiable."',
    'demo.row3.cue':       'Evidence card opens · SAR + AIS + Telegram',
    'demo.row4.script':    '"The Devil\'s Advocate has the floor."',
    'demo.row4.cue':       'Adversarial review · no rebuttal logged',
    'demo.row5.script':    '"This is the audit chain. Every action. Every model call."',
    'demo.row5.cue':       'Merkle log — 41 entries verified',
    'demo.row6.script':    '"Now switch to the local model. No code change."',
    'demo.row6.cue':       'Provider toggle · Gemini → Ollama',
    'demo.row7.script':    '"On the chain. Always."',
    'demo.row7.cue':       'Closing frame — Σ glyph',

    'arch.label':          '§ 08 · ARCHITECTURE',
    'arch.h2.a':           'One diagram.',
    'arch.h2.b':           'Every block sovereign, every connection auditable.',
    'arch.caption':        'Every block runs on free, public, sovereign components. Every connection is auditable.',
    'arch.col.sense':      'SENSE',
    'arch.col.fuse':       'FUSE · REASON',
    'arch.col.surface':    'SURFACE',
    'arch.foot':           'SOVEREIGN STACK · GREEK INFRASTRUCTURE · ZERO EGRESS',

    'close.label':         '§ 09 · THE PITCH',
    'close.line.a':        '"The question for EYP is not whether they can',
    'close.line.b':        'afford Damocles.',
    'close.line.c':        ' It is whether they can ',
    'close.line.d':        'afford not to have it."',
    'close.cta.book':      'Book the demo · 5 minutes',
    'close.cta.enter':     'Enter the platform',
    'close.link.docs':     'docs.damocles.gr',
    'close.link.email':    'contact@damocles.gr',

    'footer.build':        'BUILD · 02.MAY.2026',
    'footer.sov':          'SOVEREIGN · GREEK INFRASTRUCTURE',
    'footer.lic':          'LICENSE · MIT (FRONTEND) · AGPL-3.0 (CORE)',
    'footer.eyp':          'EYP NATIONAL SECURITY INNOVATION CHALLENGE 2026',
  },
  el: {
    'topbar.capabilities': 'Δυνατότητες',
    'topbar.architecture': 'Αρχιτεκτονική',
    'topbar.demo':         'Επίδειξη',
    'topbar.contact':      'Επικοινωνία',
    'topbar.enter':        'Είσοδος στην πλατφόρμα',
    'topbar.lang':         'EN',

    'hero.eyebrow':        'ΕΥΠ · ΕΘΝΙΚΗ ΠΡΟΚΛΗΣΗ ΚΑΙΝΟΤΟΜΙΑΣ ΑΣΦΑΛΕΙΑΣ 2026',
    'hero.h1.line1':       'Τεκμηριωμένη πληροφορία,',
    'hero.h1.line2':       'στον ρυθμό της απειλής.',
    'hero.subhead':        'Κυρίαρχη πλατφόρμα ανάλυσης που συγχωνεύει SAR, AIS, GDELT και Telegram σε γράφο γνώσης με αλυσιδωτό έλεγχο Merkle. Φτιαγμένο στα ελληνικά, σε τρεις εβδομάδες, με 1.500€.',
    'hero.cta.demo':       'Παρακολουθήστε την επίδειξη',
    'hero.cta.arch':       'Δείτε την αρχιτεκτονική',
    'hero.cta.enter':      'Είσοδος στην πλατφόρμα',
    'hero.scroll':         'ΚΥΛΗΣΗ',
    'hero.live':           'ΖΩΝΤΑΝΑ · ΑΙΓΑΙΟ 25.5°Α 37.5°Β',
    'hero.sources':        ['SAR · SENTINEL-1', 'AIS · AISSTREAM', 'GDELT 2.0', 'TELEGRAM'],

    'problem.label':       '§ 02 · ΤΟ ΠΡΟΒΛΗΜΑ',
    'problem.stat1':       'σήματα στην ουρά ενός αναλυτή σήμερα',
    'problem.stat2':       'που θα εξετάσει μέχρι το τέλος της βάρδιας',
    'problem.stat3':       'το ποσοστό κάλυψης',
    'problem.lead':        'Η σύγχρονη πληροφόρηση είναι πρόβλημα διαλογής μεταμφιεσμένο σε πρόβλημα πληροφορίας.',
    'problem.body':        'Ο Δαμοκλής αλλάζει αυτόν τον αριθμό — δρομολογώντας κάθε σήμα μέσα από ένα διαφανές επίπεδο πρακτόρων που αναδεικνύει μόνο ό,τι είναι τεκμηριωμένο, παραπεμπόμενο και αμφισβητημένο.',

    'cite.label':          '§ 03 · Η ΑΛΥΣΙΔΑ ΠΑΡΑΠΟΜΠΩΝ',
    'cite.h2.line1':       'Όχι περίληψη της περίληψης.',
    'cite.h2.line2':       'Μια αλυσίδα παραπομπών — το ίδιο πρότυπο που θα περίμενε ένα δικαστήριο.',
    'cite.brief.label':    'ΑΝΑΦΟΡΑ · 04.ΜΑΪ.2026 · 06:14 EEST',
    'cite.brief.audit':    'ΑΛΥΣΙΔΑ ΕΛΕΓΧΟΥ ΕΓΚΥΡΗ',
    'cite.brief.bluf':     'ΣΥΝΟΨΗ',
    'cite.brief.before':   'Δύο σκάφη χωρίς σημαία',
    'cite.brief.cited':    'περιφέρονται βόρεια της Λήμνου',
    'cite.brief.after':    'για 38 ώρες, με τους πομπούς AIS κλειστούς από τις 23:11.',
    'cite.brief.sources':  'ΠΗΓΕΣ · 3',
    'cite.brief.src1':     'Sentinel-1 SAR · 04.05.26 04:42Z',
    'cite.brief.src2':     'AISStream · κενό πομπού 38ω12λ',
    'cite.brief.src3':     'Telegram · @aegean-watch · 02:18',
    'cite.brief.foot1':    'ΕΠΟΠΤΗΣ: επιβεβαιωμένο',
    'cite.brief.foot2':    'ΣΥΝΗΓΟΡΟΣ ΤΟΥ ΔΙΑΒΟΛΟΥ: χωρίς αντίρρηση',
    'cite.map.label':      'ΧΑΡΤΗΣ · ΤΕΤΑΡΤΗΜΟΡΙΟ ΛΗΜΝΟΥ',
    'cite.map.coord':      '39.94°Β · 25.31°Α',
    'cite.graph.label':    'ΓΡΑΦΟΣ ΓΝΩΣΗΣ',
    'cite.graph.count':    '3 / 12.408 ΚΟΜΒΟΙ',
    'cite.evidence.label': 'ΤΕΚΜΗΡΙΟ · ΕΙΚΟΝΑ SAR',
    'cite.evidence.id':    'S1A_IW_GRDH · 04.05.26 04:42Z',
    'cite.evidence.hash':  'SHA-256: ddc1f9...',
    'cite.evidence.ok':    'ΕΠΑΛΗΘΕΥΜΕΝΟ',
    'cite.kicker':         ['Ένα κλικ. Τρεις πηγές.', 'Καμία παραίσθηση.'],
    'cite.body':           'Κάθε πρόταση σε κάθε αναφορά οδηγεί σε έναν κόμβο του γράφου γνώσης. Πατήστε μια πρόταση και ο χάρτης πετάει στις συντεταγμένες της πηγής, ο γράφος φωτίζει τον κόμβο, και το ωμό τεκμήριο — SAR, άρθρο, ή μήνυμα Telegram — ανοίγει δίπλα στην αναφορά.',

    'pipe.label':          '§ 04 · Η ΑΛΥΣΙΔΑ ΕΠΕΞΕΡΓΑΣΙΑΣ',
    'pipe.h2.a':           'Από το σήμα στην',
    'pipe.h2.b':           'υπογεγραμμένη αναφορά',
    'pipe.h2.c':           'σε πέντε βήματα.',
    'pipe.s1.title':       'Αίσθηση',
    'pipe.s1.body':        'Sentinel-1 SAR · AIS · GDELT · Telegram',
    'pipe.s2.title':       'Συγχώνευση',
    'pipe.s2.body':        'Χωροχρονική συσχέτιση, κανόνες βαθμίδας απειλής',
    'pipe.s3.title':       'Συλλογισμός',
    'pipe.s3.body':        '5 LLM πράκτορες παράλληλα',
    'pipe.s4.title':       'Αντίρρηση',
    'pipe.s4.body':        'Αντιπαραθετικός έλεγχος από Συνήγορο του Διαβόλου',
    'pipe.s5.title':       'Υπογραφή',
    'pipe.s5.body':        'Καταγραφή ελέγχου με αλυσίδα Merkle',

    'caps.label':          '§ 05 · ΦΑΣΗ 2 · ΕΠΙΧΕΙΡΗΣΙΑΚΗ',
    'caps.h2.a':           'Έξι δυνατότητες που',
    'caps.h2.b':           'καθιερώνουν τον σκεπτικισμό.',
    'caps.label.tag':      'ΔΥΝΑΤΟΤΗΤΑ',
    'caps.c1.title':       'Πανελλαδική μόνιμη κάλυψη',
    'caps.c1.body':        'Καθημερινή σάρωση 7 ημερών αποθηκευμένη σε αποθήκη γεγονότων DuckDB. Καμία επανάκτηση ανά παρακολούθηση. Η χώρα παρατηρείται συνεχώς, όχι κατ\' απαίτηση.',
    'caps.c2.title':       'Περιοχές Ενδιαφέροντος ορισμένες από AI',
    'caps.c2.body':        'Συσταδοποίηση HDBSCAN και κοίλες περιβάλλουσες alpha-shape, ονομασμένες στα ελληνικά από LLM με τεκμηριωμένη συλλογιστική.',
    'caps.c3.title':       'Πολύγωνα σχεδιασμένα από αναλυτή',
    'caps.c3.body':        'terra-draw πάνω στον MapLibre. Κάθε περιοχή που ορίζει ο αναλυτής γίνεται ισότιμος πολίτης του γράφου γνώσης.',
    'caps.c4.title':       'Γράφος γνώσης σε WebGL',
    'caps.c4.body':        'Renderer Sigma.js που κλιμακώνει πέρα από δέκα χιλιάδες κόμβους χωρίς απώλεια καρέ. Ο γράφος είναι η διεπαφή.',
    'caps.c5.title':       'Πλούσιος χάρτης σε επίπεδα',
    'caps.c5.body':        'Πορείες σκαφών, σημασιολογικά εικονίδια, δορυφορικός χάρτης βάσης, θερμικός χάρτης ειδήσεων. Κάθε επίπεδο εναλλάσσεται, κάθε επίπεδο τεκμηριώνεται.',
    'caps.c6.title':       'Αλυσίδα ελέγχου ανθεκτική σε αλλοίωση',
    'caps.c6.body':        'Κάθε κλήση μοντέλου, κάθε ενέργεια αναλυτή, χασαρισμένη και αλυσιδωμένη Merkle σε δύο αποθήκες. Κάθε κοινοβουλευτική επιτροπή μπορεί να επαληθεύσει ότι το αρχείο δεν έχει αλλοιωθεί — στην αλυσίδα. Πάντα.',
    'caps.aoi.placename':  'ΒΟΡΕΙΟ ΑΙΓΑΙΟ',

    'numbers.label':       '§ 06 · ΟΙ ΑΡΙΘΜΟΙ',
    'numbers.n1':          'για να τρέξει',
    'numbers.n2':          'συνολικός εξοπλισμός',
    'numbers.n3.suffix':   ' εβδομάδες',
    'numbers.n3':          'χρόνος ανάπτυξης',
    'numbers.n4':          'ελληνικά bytes που εξέρχονται από ελληνική υποδομή',
    'numbers.n4.sub':      '(παραγωγή)',
    'numbers.n5':          'πράκτορες στο επίπεδο συλλογισμού',
    'numbers.n6':          'εγγραφές αλυσίδας ελέγχου επαληθευμένες προ της παρουσίασης',
    'numbers.kicker.a':    'Αυτοί είναι οι αριθμοί που δεν αλλάζουν. Είναι επίσης οι αριθμοί που',
    'numbers.kicker.b':    'η Palantir δεν μπορεί να συναγωνιστεί.',

    'demo.label':          '§ 07 · ΠΩΣ ΠΡΟΣΓΕΙΩΝΕΤΑΙ Η ΕΠΙΔΕΙΞΗ',
    'demo.h2.a':           'Πέντε λεπτά.',
    'demo.h2.b':           'Επτά χτύποι.',
    'demo.row1.script':    '«Άνοιξε την αναφορά. Διάβασε τη Σύνοψη.»',
    'demo.row1.cue':       'Πάνελ αναφοράς — Σύνοψη ορατή',
    'demo.row2.script':    '«Πάτα την υπογραμμισμένη πρόταση. Δες τον χάρτη να πετάει.»',
    'demo.row2.cue':       'Ο χάρτης πετάει στο τεταρτημόριο της Λήμνου',
    'demo.row3.script':    '«Τρεις πηγές. Κάθε μία επαληθεύσιμη.»',
    'demo.row3.cue':       'Κάρτα τεκμηρίου ανοίγει · SAR + AIS + Telegram',
    'demo.row4.script':    '«Ο Συνήγορος του Διαβόλου έχει τον λόγο.»',
    'demo.row4.cue':       'Αντιπαραθετικός έλεγχος · χωρίς καταγεγραμμένη αντίρρηση',
    'demo.row5.script':    '«Αυτή είναι η αλυσίδα ελέγχου. Κάθε ενέργεια. Κάθε κλήση μοντέλου.»',
    'demo.row5.cue':       'Καταγραφή Merkle — 41 εγγραφές επαληθευμένες',
    'demo.row6.script':    '«Τώρα γύρνα στο τοπικό μοντέλο. Καμία αλλαγή κώδικα.»',
    'demo.row6.cue':       'Εναλλαγή παρόχου · Gemini → Ollama',
    'demo.row7.script':    '«Στην αλυσίδα. Πάντα.»',
    'demo.row7.cue':       'Καρέ κλεισίματος — γλύφος Σ',

    'arch.label':          '§ 08 · ΑΡΧΙΤΕΚΤΟΝΙΚΗ',
    'arch.h2.a':           'Ένα διάγραμμα.',
    'arch.h2.b':           'Κάθε μπλοκ κυρίαρχο, κάθε σύνδεση ελέγξιμη.',
    'arch.caption':        'Κάθε μπλοκ τρέχει σε ελεύθερα, δημόσια, κυρίαρχα στοιχεία. Κάθε σύνδεση είναι ελέγξιμη.',
    'arch.col.sense':      'ΑΙΣΘΗΣΗ',
    'arch.col.fuse':       'ΣΥΓΧΩΝΕΥΣΗ · ΣΥΛΛΟΓΙΣΜΟΣ',
    'arch.col.surface':    'ΕΠΙΦΑΝΕΙΑ',
    'arch.foot':           'ΚΥΡΙΑΡΧΗ ΣΤΟΙΒΑ · ΕΛΛΗΝΙΚΗ ΥΠΟΔΟΜΗ · ΜΗΔΕΝΙΚΗ ΕΞΟΔΟΣ',

    'close.label':         '§ 09 · Η ΠΡΟΤΑΣΗ',
    'close.line.a':        '«Το ερώτημα για την ΕΥΠ δεν είναι αν μπορεί να',
    'close.line.b':        'πληρώσει τον Δαμοκλή.',
    'close.line.c':        ' Είναι αν μπορεί να ',
    'close.line.d':        'στερηθεί τον Δαμοκλή.»',
    'close.cta.book':      'Κλείστε την επίδειξη · 5 λεπτά',
    'close.cta.enter':     'Είσοδος στην πλατφόρμα',
    'close.link.docs':     'docs.damocles.gr',
    'close.link.email':    'contact@damocles.gr',

    'footer.build':        'ΕΚΔΟΣΗ · 02.ΜΑΪ.2026',
    'footer.sov':          'ΚΥΡΙΑΡΧΟ · ΕΛΛΗΝΙΚΗ ΥΠΟΔΟΜΗ',
    'footer.lic':          'ΑΔΕΙΑ · MIT (FRONTEND) · AGPL-3.0 (CORE)',
    'footer.eyp':          'ΕΥΠ ΕΘΝΙΚΗ ΠΡΟΚΛΗΣΗ ΚΑΙΝΟΤΟΜΙΑΣ ΑΣΦΑΛΕΙΑΣ 2026',
  },
};

const LangContext = React.createContext({ lang: 'en', setLang: () => {}, t: (k) => k });

function LangProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem('damocles.lang') || 'en'; } catch { return 'en'; }
  });
  useEffect(() => {
    try { localStorage.setItem('damocles.lang', lang); } catch {}
    document.documentElement.lang = lang;
  }, [lang]);
  const t = useCallback((key) => {
    const dict = I18N[lang] || I18N.en;
    return dict[key] ?? I18N.en[key] ?? key;
  }, [lang]);
  return (
    <LangContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LangContext.Provider>
  );
}

function useT() {
  return React.useContext(LangContext);
}

// Tiny toggle: shows the OTHER language as the click-to-switch label.
function LangSwitch({ style = {} }) {
  const { lang, setLang } = useT();
  const other = lang === 'en' ? 'el' : 'en';
  const label = other.toUpperCase();
  return (
    <button
      onClick={() => setLang(other)}
      title={lang === 'en' ? 'Αλλαγή στα ελληνικά' : 'Switch to English'}
      style={{
        background: 'transparent',
        border: '1px solid var(--panel-border)',
        color: '#94a3b8',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        letterSpacing: '0.12em',
        padding: '5px 9px',
        borderRadius: 2,
        cursor: 'pointer',
        transition: 'all 200ms ease',
        ...style,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.color = '#f59e0b'; e.currentTarget.style.borderColor = '#f59e0b'; }}
      onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.borderColor = 'var(--panel-border)'; }}
    >
      {label}
    </button>
  );
}

window.LangProvider = LangProvider;
window.LangContext = LangContext;
window.LangSwitch = LangSwitch;
window.useT = useT;
