import {
  Lock,
  Database,
  Cpu,
  Mic,
  ShieldCheck,
  FileText,
  ArrowRight,
  Sparkles,
  Zap,
  Github,
  CheckCircle2,
} from "lucide-react";

export default function Home() {
  return (
    <main className="relative overflow-hidden">
      {/* ─── Glow backdrop ─── */}
      <div
        className="glow w-[640px] h-[640px] -top-40 -left-40 opacity-50"
        style={{ background: "radial-gradient(circle, #ff6a26 0%, transparent 70%)" }}
      />
      <div
        className="glow w-[480px] h-[480px] top-[20%] right-[-10%] opacity-30"
        style={{ background: "radial-gradient(circle, #5ec8ff 0%, transparent 70%)" }}
      />

      {/* ─── Nav ─── */}
      <nav className="relative z-20 max-w-6xl mx-auto px-6 md:px-10 py-6 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Logo />
          <span className="font-display text-2xl tracking-tight">revvec</span>
        </div>
        <div className="hidden md:flex items-center gap-7 text-[13.5px] text-ink/70">
          <a href="#why" className="hover:text-ink transition-colors">why on-device</a>
          <a href="#how" className="hover:text-ink transition-colors">how it works</a>
          <a href="#stack" className="hover:text-ink transition-colors">stack</a>
          <a href="#compliance" className="hover:text-ink transition-colors">compliance</a>
        </div>
        <a
          href="https://github.com/yrevash/revvec"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 text-[13px] text-ink/80 hover:text-ink border border-ink/15 rounded-full px-3 py-1.5 hover:border-ink/30 transition-colors"
        >
          <Github size={13} /> repo
        </a>
      </nav>

      {/* ─── Hero ─── */}
      <section className="relative z-10 max-w-6xl mx-auto px-6 md:px-10 pt-12 md:pt-24 pb-20 md:pb-32">
        <h1 className="font-display text-[52px] md:text-[88px] leading-[0.95] tracking-tight max-w-5xl">
          Airgapped industrial RAG.
          <br />
          <span className="italic text-ink/55">On‑device. </span>
          <span className="gradient-text">No cloud.</span>
        </h1>
        <p className="mt-8 max-w-2xl text-[18px] md:text-[20px] leading-relaxed text-ink/75">
          Your SOPs, sensor streams, and mission documents cannot touch a cloud LLM.
          <span className="text-ink"> CMMC. ITAR. 21 CFR Part 11. NIS2. </span>
          revvec runs every model, every embedding, and every byte of your data on a single Mac. Nothing leaves the box.
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-3">
          <a
            href="#how"
            className="group inline-flex items-center gap-2 px-5 py-3 bg-ink text-white rounded-full font-medium text-[14px] hover:bg-ink/85 transition-all shadow-sm"
          >
            See how it works
            <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" />
          </a>
          <a
            href="#demo"
            className="inline-flex items-center gap-2 px-5 py-3 bg-white/80 backdrop-blur text-ink rounded-full font-medium text-[14px] border border-ink/15 hover:border-ink/30 transition-all"
          >
            Watch the demo
          </a>
        </div>

        {/* Stats strip */}
        <div className="mt-20 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-8 max-w-4xl">
          <Stat n="68 ms" l="P95 retrieval" />
          <Stat n="9 ms" l="cache hit P95" />
          <Stat n="0" l="fabricated citations" />
          <Stat n="3.1 MB" l=".dmg, fully offline" />
        </div>
      </section>

      {/* ─── Why ─── */}
      <section id="why" className="relative z-10 border-t border-ink/8 bg-white/40 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-24">
          <SectionLabel icon={<Lock size={11} />}>Why on-device</SectionLabel>
          <h2 className="font-display text-4xl md:text-6xl leading-[1.05] tracking-tight max-w-4xl mb-4">
            Cloud RAG is illegal in the rooms that matter.
          </h2>
          <p className="text-[17px] text-ink/70 max-w-2xl mb-14">
            Defense, aerospace, pharma, semiconductor, EU critical infrastructure, every one of them has
            a regulation that bans CUI, technical data, or operational records from leaving an approved
            boundary. revvec is built around that line.
          </p>

          <div className="grid md:grid-cols-2 gap-px bg-ink/8 rounded-2xl overflow-hidden border border-ink/8">
            {REGULATIONS.map((r) => (
              <div key={r.code} className="bg-white p-7">
                <div className="flex items-baseline justify-between mb-3">
                  <div className="font-mono text-[11px] text-accent uppercase tracking-[0.1em]">
                    {r.code}
                  </div>
                  <div className="text-[11px] text-ink/50">{r.where}</div>
                </div>
                <div className="font-display text-2xl tracking-tight mb-2">{r.title}</div>
                <p className="text-[14.5px] text-ink/70 leading-relaxed">{r.body}</p>
              </div>
            ))}
          </div>

          <div className="mt-12 grid md:grid-cols-3 gap-4">
            <Headline kicker="Nov 2025" line="CMMC 2.0 enforcement live" />
            <Headline kicker="Mar 2026" line="DoD bans Anthropic" />
            <Headline kicker="2025" line="TSMC 2nm leak, $40M" />
          </div>
        </div>
      </section>

      {/* ─── How it works ─── */}
      <section id="how" className="relative z-10 border-t border-ink/8">
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-24">
          <SectionLabel icon={<Sparkles size={11} />}>How it works</SectionLabel>
          <h2 className="font-display text-4xl md:text-6xl leading-[1.05] tracking-tight max-w-4xl mb-3">
            Five stages. One Mac. <em className="text-accent not-italic">Zero hops.</em>
          </h2>
          <p className="text-[17px] text-ink/70 max-w-2xl mb-14">
            Inputs, embeddings, storage, retrieval, response, every box runs on the same machine.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {PIPELINE.map((p, i) => (
              <PipeCard key={p.title} step={i + 1} {...p} />
            ))}
          </div>

          <div className="mt-14 grid md:grid-cols-3 gap-4">
            <BigClaim
              icon={<Database size={16} />}
              kicker="Actian VectorAI DB"
              title="3 named vectors / point"
              body="A PDF page is one record holding both a text vector AND an image vector with a shared payload. No four-database federation."
            />
            <BigClaim
              icon={<Zap size={16} />}
              kicker="Server-side fusion"
              title="RRF in one round-trip"
              body="Reciprocal Rank Fusion across all named vectors via points.query(prefetch=…). ~15 ms for stage 1 on a 1,940-point corpus."
            />
            <BigClaim
              icon={<ShieldCheck size={16} />}
              kicker="Hash chain"
              title="Tamper-evident audit"
              body="Every query, cache hit, and forget-request lands in a SHA-256-chained JSONL log. 6/6 tamper tests pass."
            />
          </div>
        </div>
      </section>

      {/* ─── Stack ─── */}
      <section id="stack" className="relative z-10 border-t border-ink/8 bg-deep text-white">
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-24">
          <SectionLabel icon={<Cpu size={11} />} dark>The stack</SectionLabel>
          <h2 className="font-display text-4xl md:text-6xl leading-[1.05] tracking-tight max-w-4xl mb-3">
            Best-in-class small models, <span className="italic text-accent">all local.</span>
          </h2>
          <p className="text-[17px] text-white/65 max-w-2xl mb-14">
            Picked April 2026 as the strongest per-GB choice for Apple Silicon. Apache-2.0 or ungated.
            No HuggingFace API at runtime, weights live in the local cache.
          </p>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {STACK.map((s) => (
              <div
                key={s.name}
                className="rounded-2xl border border-white/10 p-6 bg-white/[0.02] hover:bg-white/[0.04] transition-colors"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="font-mono text-[10.5px] text-accent uppercase tracking-[0.12em]">
                    {s.slot}
                  </div>
                  <div className="font-mono text-[11px] text-white/45">{s.size}</div>
                </div>
                <div className="font-display text-2xl mb-1">{s.name}</div>
                <div className="text-[13.5px] text-white/55 mb-4">{s.note}</div>
                <div className="text-[11px] font-mono text-white/40 uppercase tracking-wide">
                  {s.licence}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Demo ─── */}
      <section id="demo" className="relative z-10 border-t border-ink/8 gridlines">
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-24">
          <SectionLabel icon={<Mic size={11} />}>Live demo</SectionLabel>
          <h2 className="font-display text-4xl md:text-6xl leading-[1.05] tracking-tight max-w-4xl mb-12">
            Watch the airgap hold under pressure.
          </h2>

          <div className="rounded-3xl overflow-hidden border border-ink/10 bg-white shadow-[0_20px_80px_-30px_rgba(255,106,38,0.18)]">
            <div className="aspect-video relative bg-ink">
              <iframe
                className="absolute inset-0 w-full h-full"
                src="https://www.youtube.com/embed/h3Z-lNdBV6o?rel=0&modestbranding=1"
                title="revvec, airgapped industrial RAG demo"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                referrerPolicy="strict-origin-when-cross-origin"
                allowFullScreen
              />
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between text-[11.5px] text-ink/55 font-mono">
            <span>3 min · airgap proven on camera</span>
            <a
              href="https://youtu.be/h3Z-lNdBV6o"
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline"
            >
              open on YouTube ↗
            </a>
          </div>

          <div className="mt-12 grid md:grid-cols-3 gap-4">
            {DEMO_BEATS.map((b) => (
              <div key={b.t} className="bg-white border border-ink/8 rounded-2xl p-6">
                <div className="font-mono text-[10.5px] text-accent uppercase tracking-[0.12em] mb-2">
                  {b.t}
                </div>
                <div className="font-display text-xl mb-1.5">{b.title}</div>
                <p className="text-[13.5px] text-ink/65 leading-relaxed">{b.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Compliance ─── */}
      <section id="compliance" className="relative z-10 border-t border-ink/8 bg-white/40">
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-24">
          <SectionLabel icon={<FileText size={11} />}>Compliance posture</SectionLabel>
          <div className="grid md:grid-cols-5 gap-10 items-start">
            <div className="md:col-span-3">
              <h2 className="font-display text-4xl md:text-6xl leading-[1.05] tracking-tight mb-5">
                Defensible by construction.
              </h2>
              <p className="text-[17px] text-ink/70 mb-6 leading-relaxed">
                We don't gesture at compliance. <code className="font-mono text-[14px] bg-ink text-white px-1.5 py-0.5 rounded">docs/compliance.md</code> maps every feature
                to a clause with a `file:line` citation. Honest about what's still v0.1 (no auth on admin endpoints; <code className="font-mono text-[13px] bg-ink/5 px-1 rounded">vde.save_snapshot</code> UNIMPLEMENTED).
              </p>
              <ul className="space-y-3">
                {COMPLIANCE.map((c) => (
                  <li key={c.code} className="flex gap-3.5 items-start">
                    <CheckCircle2 size={16} className="text-accent mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="font-mono text-[11px] text-accent uppercase tracking-[0.1em]">{c.code}</div>
                      <div className="text-[15px] text-ink/85">{c.line}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="md:col-span-2">
              <CodeTerminal />
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section className="relative z-10 border-t border-ink/8 bg-deep text-white">
        <div
          className="glow w-[600px] h-[600px] left-[50%] -translate-x-1/2 -bottom-72 opacity-30"
          style={{ background: "radial-gradient(circle, #ff6a26 0%, transparent 70%)" }}
        />
        <div className="relative max-w-4xl mx-auto px-6 md:px-10 py-28 text-center">
          <h2 className="font-display text-5xl md:text-7xl leading-[1] tracking-tight mb-6">
            Pull the cable. <span className="italic text-accent">Still works.</span>
          </h2>
          <p className="text-[18px] text-white/70 max-w-2xl mx-auto mb-10">
            One Mac app. One Actian collection. Three named vectors. Zero cloud calls in the source tree.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <a
              href="https://github.com/yrevash/revvec"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 px-6 py-3 bg-white text-ink rounded-full font-medium text-[14px] hover:bg-white/90 transition-all"
            >
              <Github size={15} /> GitHub repo
            </a>
            <a
              href="#demo"
              className="inline-flex items-center gap-2 px-6 py-3 border border-white/20 rounded-full font-medium text-[14px] hover:border-white/40 transition-all"
            >
              Watch the 3-min demo
            </a>
          </div>
        </div>
      </section>

      <footer className="relative z-10 border-t border-ink/8 bg-white/40">
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-10 flex flex-col md:flex-row items-center justify-between gap-4 text-[12px] text-ink/55">
          <div className="flex items-center gap-2.5">
            <Logo small />
            <span>revvec · Apache-2.0</span>
          </div>
          <div className="font-mono">Apple Silicon · MLX · Actian VectorAI · FastAPI · Tauri</div>
        </div>
      </footer>
    </main>
  );
}

function CodeTerminal() {
  const lines: Array<{ t: string; tone?: "dim" | "ok" | "err" | "accent" }> = [
    { t: "# tamper test", tone: "dim" },
    { t: "$ curl localhost:8000/api/admin/audit" },
    { t: '{"chain_ok": true}', tone: "ok" },
    { t: " " },
    { t: "$ echo tampered >> data/audit/2026-04-25.jsonl", tone: "accent" },
    { t: " " },
    { t: "$ curl localhost:8000/api/admin/audit" },
    { t: '{"chain_ok": false}', tone: "err" },
  ];
  const tones: Record<string, string> = {
    dim: "text-white/40",
    ok: "text-emerald-400",
    err: "text-red-400",
    accent: "text-accent",
  };
  return (
    <pre className="bg-ink text-white/85 rounded-2xl p-6 text-[12.5px] font-mono leading-[1.8] overflow-x-auto">
      {lines.map((l, i) => (
        <div key={i} className={l.tone ? tones[l.tone] : ""}>
          {l.t || " "}
        </div>
      ))}
    </pre>
  );
}

/* ─── Small components ─── */

function Logo({ small = false }: { small?: boolean }) {
  const size = small ? 22 : 30;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className="flex-shrink-0"
      aria-hidden
    >
      <defs>
        <linearGradient id="rv" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#0a0a0b" />
          <stop offset="100%" stopColor="#ff6a26" />
        </linearGradient>
      </defs>
      <text
        x="50%"
        y="58%"
        textAnchor="middle"
        dominantBaseline="middle"
        fontFamily="Instrument Serif, serif"
        fontWeight="700"
        fontSize="22"
        fill="url(#rv)"
      >
        rv
      </text>
    </svg>
  );
}

function Stat({ n, l }: { n: string; l: string }) {
  return (
    <div>
      <div className="font-display text-4xl md:text-5xl tracking-tight">{n}</div>
      <div className="text-[12px] text-ink/55 mt-1.5 font-mono uppercase tracking-[0.08em]">{l}</div>
    </div>
  );
}

function SectionLabel({
  children,
  icon,
  dark = false,
}: {
  children: React.ReactNode;
  icon?: React.ReactNode;
  dark?: boolean;
}) {
  return (
    <div
      className={
        "inline-flex items-center gap-1.5 mb-6 px-2.5 py-1 rounded-full border text-[11px] font-mono uppercase tracking-[0.12em] " +
        (dark
          ? "border-white/15 text-white/60 bg-white/5"
          : "border-ink/12 text-ink/65 bg-white/70")
      }
    >
      {icon}
      <span>{children}</span>
    </div>
  );
}

function PipeCard({
  step,
  title,
  body,
  items,
}: {
  step: number;
  title: string;
  body: string;
  items: string[];
}) {
  return (
    <div className="bg-white rounded-2xl border border-ink/8 p-5 hover:border-accent/30 transition-colors group">
      <div className="font-mono text-[10.5px] text-ink/40 mb-3">STAGE 0{step}</div>
      <div className="font-display text-xl mb-2 group-hover:text-accent transition-colors">{title}</div>
      <p className="text-[13px] text-ink/65 leading-relaxed mb-4">{body}</p>
      <ul className="space-y-1.5">
        {items.map((it) => (
          <li key={it} className="text-[12px] text-ink/70 font-mono flex items-start gap-1.5">
            <span className="text-accent mt-0.5">·</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function BigClaim({
  icon,
  kicker,
  title,
  body,
}: {
  icon: React.ReactNode;
  kicker: string;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-2xl border border-ink/10 bg-white p-6">
      <div className="flex items-center gap-2 text-accent mb-3">{icon}<span className="font-mono text-[10.5px] uppercase tracking-[0.12em]">{kicker}</span></div>
      <div className="font-display text-2xl tracking-tight mb-2">{title}</div>
      <p className="text-[14px] text-ink/70 leading-relaxed">{body}</p>
    </div>
  );
}

function Headline({ kicker, line }: { kicker: string; line: string }) {
  return (
    <div className="rounded-xl border border-ink/8 bg-white p-5">
      <div className="font-mono text-[10.5px] text-accent uppercase tracking-[0.12em] mb-1.5">{kicker}</div>
      <div className="text-[15px] text-ink/85">{line}</div>
    </div>
  );
}

/* ─── Content data ─── */

const REGULATIONS = [
  {
    code: "CMMC 2.0",
    where: "US DoD",
    title: "Defense contractor data",
    body: "Controlled Unclassified Information must stay inside an approved environment. Sending data to a cloud LLM is loss of control + compliance violation.",
  },
  {
    code: "ITAR",
    where: "22 CFR 120",
    title: "US defense export",
    body: "Technical data on the US Munitions List cannot leave US soil or be accessible to foreign entities. Cloud APIs route globally, that's an illegal export.",
  },
  {
    code: "21 CFR Part 11",
    where: "FDA",
    title: "Pharma electronic records",
    body: "Audit trails, data integrity, tamper-proof logs. Cloud LLMs lack verifiable audit and traceability guarantees.",
  },
  {
    code: "NIS2",
    where: "EU",
    title: "Critical infrastructure",
    body: "Operational data security and supply-chain risk management. External AI services introduce a third-party risk surface critical infrastructure can't absorb.",
  },
];

const PIPELINE = [
  {
    title: "Inputs",
    body: "PDFs, images, sensor windows, and live voice. Real industrial shapes.",
    items: ["PDF SOPs", "NASA images", "CMAPSS sensors", "voice mic"],
  },
  {
    title: "Embed",
    body: "Five small models, lazy-loaded with TTL unload. All MLX-native.",
    items: ["Qwen3 text 1024d", "DINOv2 image 1024d", "Chronos sensor 512d", "Whisper ASR"],
  },
  {
    title: "Store",
    body: "One collection, three named vectors per point, schema locked at create-time.",
    items: ["Actian VectorAI", "3 vectors / point", "schema-validated", "pattern promotion"],
  },
  {
    title: "Retrieve",
    body: "Server-side RRF fusion + client-side hybrid rerank with code-aware regex.",
    items: ["3-tier hybrid", "RRF + lexical", "Qwen3-4B MLX", "answer cache"],
  },
  {
    title: "Respond",
    body: "Streaming tokens with [source:N] pills, voice synthesis, audited.",
    items: ["Tauri desktop", "4 personas", "streaming SSE", "Kokoro TTS"],
  },
];

const STACK = [
  {
    slot: "LLM",
    name: "Qwen3-4B-Instruct-2507",
    note: "4-bit MLX. ~3.5 GB active. Streams 60–90 tok/s on M-series.",
    licence: "Apache-2.0",
    size: "3.5 GB",
  },
  {
    slot: "Text embed",
    name: "Qwen3-Embedding-0.6B",
    note: "1024d Matryoshka. SOTA small embedder as of 2026.",
    licence: "Apache-2.0",
    size: "1.2 GB",
  },
  {
    slot: "Image embed",
    name: "DINOv2 ViT-L",
    note: "1024d, ungated, self-supervised. Page renders + photos.",
    licence: "Meta",
    size: "1.2 GB",
  },
  {
    slot: "Sensor embed",
    name: "Chronos-Bolt-small",
    note: "512d pooled. Time-series foundation model from Amazon.",
    licence: "Apache-2.0",
    size: "200 MB",
  },
  {
    slot: "ASR",
    name: "Whisper-large-v3-turbo",
    note: "Via mlx-whisper. ~5× real-time on Apple GPU.",
    licence: "MIT",
    size: "0.8 GB",
  },
  {
    slot: "TTS",
    name: "Kokoro-82M",
    note: "MOS 4.2, TTS Arena #1, Jan 2026.",
    licence: "Apache-2.0",
    size: "0.3 GB",
  },
];

const DEMO_BEATS = [
  {
    t: "0:30",
    title: "Tokens stream live",
    body: "Qwen3-4B generating on the Apple Silicon GPU. Every claim cites a real document by [source:N] pill.",
  },
  {
    t: "1:10",
    title: "Voice. Local.",
    body: "Whisper turbo transcribes as you speak, partial transcripts in the input field. Kokoro TTS speaks back.",
  },
  {
    t: "2:05",
    title: "Pull the cable",
    body: "Ethernet unplugged on camera. Wi-Fi off. Query still answers, still cites. The airgap holds.",
  },
];

const COMPLIANCE = [
  { code: "CMMC SP.3.1.7", line: "Limits use of non-approved external information systems" },
  { code: "21 CFR 11.10(e)", line: "Use of secure, computer-generated, time-stamped audit trails" },
  { code: "NIS2 Art. 21", line: "Data security and supply-chain risk management measures" },
  { code: "ITAR 22 CFR 120", line: "Technical data does not leave the controlled environment" },
  { code: "GDPR Art. 17", line: "Right to erasure, implemented via /api/admin/forget" },
];
