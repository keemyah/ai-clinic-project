import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Send,
  Paperclip,
  Smile,
  Mic,
  Settings,
  User,
  MessageCircle,
  Loader2,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import CraftLogo from "./assets/craft_ai_logo.svg";

const quickActions = ["Résumé", "Priorités", "Export PDF"];

const initialMessages = [
  {
    id: 1,
    who: "bot",
    text: "Bonjour 👋 — je suis ton assistant juridique connecté à LegiFrance. Pose ta question quand tu veux.",
    time: formatTime(),
  },
];

function formatTime(date = new Date()) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatTimestamp(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function stripCodeFence(raw = "") {
  const text = String(raw).trim();
  const fenced = text.match(/^```[\w+-]*\s*\n?([\s\S]*?)```$/i);
  return fenced ? fenced[1].trim() : text;
}

function tryParseJson(raw = "") {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function normalizeAnalysisPayload(raw) {
  if (!raw) return null;
  if (typeof raw === "object") return raw;
  const cleaned = stripCodeFence(raw);
  return tryParseJson(cleaned) || cleaned;
}

function normalizeAnswerText(raw) {
  const cleaned = stripCodeFence(raw || "");
  return cleaned || "Aucune réponse.";
}

function buildDebateSummary(analysis) {
  if (!analysis || typeof analysis !== "object") return "";
  const parts = [];

  if (analysis.position_pro && analysis.position_pro !== "INFORMATION_INSUFFISANTE") {
    const thesis = analysis.position_pro?.these;
    if (thesis) parts.push(`Position favorable : ${thesis}`);
    const firstArg = analysis.position_pro?.arguments?.[0]?.analyse;
    if (firstArg) parts.push(`Argument clé : ${firstArg}`);
  }

  if (analysis.position_contra && analysis.position_contra !== "INFORMATION_INSUFFISANTE") {
    const thesis = analysis.position_contra?.these;
    if (thesis) parts.push(`Position contraire : ${thesis}`);
    const firstArg = analysis.position_contra?.arguments?.[0]?.analyse;
    if (firstArg) parts.push(`Contre-argument : ${firstArg}`);
  }

  const synthese = analysis.synthese;
  if (synthese) parts.push(`Synthèse : ${synthese}`);

  return parts.join("\n\n");
}

export default function ChatbotUI() {
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [codes, setCodes] = useState([]);
  const [selectedCode, setSelectedCode] = useState(null);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => scrollToBottom(), [messages]);
  useEffect(() => {
    bootstrap();
  }, []);

  const filteredCodes = codes.filter((code) =>
    code.label.toLowerCase().includes(query.toLowerCase())
  );

  const analysisObject =
    lastResult && typeof lastResult.analysis === "object" ? lastResult.analysis : null;
  const proPosition =
    analysisObject && typeof analysisObject.position_pro === "object"
      ? analysisObject.position_pro
      : null;
  const contraPosition =
    analysisObject && typeof analysisObject.position_contra === "object"
      ? analysisObject.position_contra
      : null;
  const vigilancePoints = Array.isArray(analysisObject?.points_de_vigilance)
    ? analysisObject.points_de_vigilance
    : [];
  const renderPositionCard = (label, data, accent) => {
    if (!data || data === "INFORMATION_INSUFFISANTE") {
      return (
        <div key={label} className="rounded-xl border border-white/20 bg-white/5 p-3">
          <div className={`text-xs font-semibold ${accent}`}>{label}</div>
          <p className="text-xs text-white/70 mt-1">Information insuffisante.</p>
        </div>
      );
    }

    return (
      <div key={label} className="rounded-xl border border-white/20 bg-white/5 p-3 space-y-2">
        <div className={`text-xs font-semibold ${accent}`}>{label}</div>
        <div className="text-sm font-semibold text-white">{data.these}</div>
        <div className="text-[11px] text-white/70">
          Textes cités :{" "}
          {Array.isArray(data.textes_applicables) && data.textes_applicables.length > 0
            ? data.textes_applicables.join(", ")
            : "—"}
        </div>
        <div className="text-xs text-white space-y-2">
          {Array.isArray(data.arguments) && data.arguments.length > 0 ? (
            data.arguments.map((arg, idx) => (
              <div key={`${label}-${idx}`}>
                <div className="font-semibold">{arg.point || `Argument ${idx + 1}`}</div>
                <p className="whitespace-pre-wrap">{arg.analyse}</p>
                {Array.isArray(arg.sources) && arg.sources.length > 0 && (
                  <div className="text-[11px] text-white/60">{arg.sources.join(", ")}</div>
                )}
              </div>
            ))
          ) : (
            <p>Aucun argument détaillé.</p>
          )}
        </div>
        {Array.isArray(data.risques) && data.risques.length > 0 && (
          <div className="text-xs text-amber-200">
            Risques : {data.risques.join("; ")}
          </div>
        )}
      </div>
    );
  };

  function scrollToBottom() {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }

  async function bootstrap() {
    try {
      const [healthRes, codesRes] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/codes"),
      ]);

      if (healthRes.ok) {
        const payload = await healthRes.json();
        setBackendStatus(payload.mode || "online");
      } else {
        setBackendStatus("offline");
      }

      if (codesRes.ok) {
        const payload = await codesRes.json();
        setCodes(payload.codes || []);
      }
    } catch (err) {
      console.error(err);
      setBackendStatus("offline");
    }
  }

  async function sendMessage(e) {
    e?.preventDefault();
    if (!input.trim() || loading) return;

    const text = input.trim();
    const timestamp = formatTime();
    const next = { id: Date.now(), who: "user", text, time: timestamp };
    setMessages((prev) => [...prev, next]);
    setInput("");
    setError(null);
    setLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          code: selectedCode?.label ?? null,
        }),
      });

      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const message = payload?.detail || "Erreur serveur lors de l'appel backend.";
        throw new Error(message);
      }

      const normalizedAnalysis = normalizeAnalysisPayload(payload?.analysis);
      const cleanedAnswer = normalizeAnswerText(payload?.answer);

      const replyText =
        typeof normalizedAnalysis === "object"
          ? buildDebateSummary(normalizedAnalysis) || cleanedAnswer
          : cleanedAnswer;

      const reply = {
        id: Date.now() + 1,
        who: "bot",
        text: replyText,
        time: formatTime(),
      };
      setMessages((prev) => [...prev, reply]);
      setLastResult({
        ...payload,
        answer: cleanedAnswer,
        analysis: normalizedAnalysis,
      });
    } catch (err) {
      console.error(err);
      setError(err.message);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 2,
          who: "bot",
          text: "⚠️ Erreur pendant l'appel serveur. Merci de réessayer.",
          time: formatTime(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function toggleCodeSelection(code) {
    setSelectedCode((prev) => (prev?.id === code.id ? null : code));
  }

  return (
    <div className="h-screen w-full bg-gradient-to-br from-[#050b2a] via-[#0d1544] to-[#192c7c] flex">
      <div className="w-full h-full grid grid-cols-12 gap-6 px-6 py-4 overflow-hidden">
        {/* Left column */}
        <aside className="col-span-3 bg-white/10 backdrop-blur-lg border border-white/10 rounded-2xl shadow-xl p-4 flex flex-col gap-4 overflow-hidden text-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img src={CraftLogo} alt="Craft.AI" className="w-12 h-12 rounded-2xl bg-white/80 p-2 shadow-lg" />
              <div>
                <div className="text-sm font-semibold tracking-wide uppercase">Craft.AI Legal</div>
                <div className="text-xs text-white/80 flex items-center gap-1">
                  {backendStatus === "offline" ? (
                    <>
                      <AlertTriangle size={12} className="text-rose-300" />
                      <span>Serveur hors-ligne</span>
                    </>
                  ) : backendStatus === "checking" ? (
                    <>
                      <Loader2 size={12} className="animate-spin text-amber-300" />
                      <span>Connexion...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={12} className="text-emerald-300" />
                      <span>Connecté</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <button className="p-2 rounded-lg hover:bg-white/20" aria-label="Paramètres">
              <Settings size={18} />
            </button>
          </div>

          <label className="relative block">
            <span className="sr-only">Recherche de code</span>
            <span className="absolute inset-y-0 left-0 flex items-center pl-3">
              <Search size={16} />
            </span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="placeholder:italic placeholder:text-white/60 block bg-white/10 text-white w-full border border-white/20 rounded-md py-2 pl-10 pr-3 focus:outline-none focus:border-violet-300"
              placeholder="Rechercher un code..."
            />
          </label>

          <div className="flex-1 overflow-auto">
            <ul className="flex flex-col gap-2">
              {filteredCodes.length === 0 && (
                <li className="text-xs text-white/70 px-2">Aucun code trouvé.</li>
              )}
              {filteredCodes.map((code) => (
                <li
                  key={code.id}
                  onClick={() => toggleCodeSelection(code)}
                  className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer border ${
                    selectedCode?.id === code.id
                      ? "border-white/70 bg-white/20"
                      : "border-transparent hover:bg-white/10"
                  }`}
                >
                  <div className="w-10 h-10 bg-white/20 rounded-lg flex items-center justify-center text-sm font-medium">
                    {code.label.substring(0, 2)}
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium">{code.label}</div>
                    <div className="text-xs text-white/70">
                      {selectedCode?.id === code.id ? "Filtre actif" : "Cliquer pour filtrer"}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setSelectedCode(null)}
              className="flex-1 py-2 rounded-lg bg-white text-[#111b4d] text-sm font-semibold disabled:opacity-60"
              disabled={!selectedCode}
            >
              Tous les codes
            </button>
            <button className="py-2 px-3 rounded-lg border border-white/30 text-white" aria-label="Profil">
              <User size={16} />
            </button>
          </div>
        </aside>

        {/* Main chat area */}
        <main className="col-span-6 bg-white rounded-2xl shadow-2xl p-4 flex flex-col overflow-hidden">
          <header className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-rose-400 to-orange-400 flex items-center justify-center text-white font-bold">
              AJ
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold">Assistant juridique</div>
              <div className="text-xs text-slate-500">
                Analyse en direct • {selectedCode?.label || "Tous les codes"}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button className="p-2 rounded-md hover:bg-slate-50" aria-label="Historique">
                <MessageCircle size={18} />
              </button>
              <button className="p-2 rounded-md hover:bg-slate-50" aria-label="Paramètres">
                <Settings size={18} />
              </button>
            </div>
          </header>

          <section className="flex-1 overflow-auto py-4 px-2" aria-live="polite">
            <ul className="flex flex-col gap-3 max-h-[60vh]">
              <AnimatePresence initial={false} mode="popLayout">
                {messages.map((m) => (
                  <motion.li
                    key={m.id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className={`flex ${m.who === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`${
                        m.who === "user"
                          ? "bg-indigo-600 text-white rounded-2xl rounded-br-none"
                          : "bg-slate-100 text-slate-800 rounded-2xl rounded-tl-none"
                      } max-w-[75%] p-3 shadow-sm`}
                    >
                      <div className="text-sm leading-relaxed whitespace-pre-wrap">{m.text}</div>
                      <div
                        className={`text-[11px] mt-2 ${
                          m.who === "user" ? "text-indigo-100" : "text-slate-400"
                        } text-right`}
                      >
                        {m.time}
                      </div>
                    </div>
                  </motion.li>
                ))}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </ul>
          </section>

          <form onSubmit={sendMessage} className="pt-3 border-t border-slate-100">
            <div className="flex items-end gap-2">
              <button type="button" className="p-2 rounded-lg hover:bg-slate-50" aria-label="Attacher">
                <Paperclip size={18} />
              </button>
              <button type="button" className="p-2 rounded-lg hover:bg-slate-50" aria-label="Emoji">
                <Smile size={18} />
              </button>

              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Écris un message..."
                className="flex-1 bg-slate-50 rounded-2xl py-3 px-4 focus:outline-none"
              />

              <button
                type="submit"
                className="ml-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-2xl px-4 py-2 flex items-center gap-2"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span className="hidden sm:inline text-sm">Analyse...</span>
                  </>
                ) : (
                  <>
                    <Send size={16} />
                    <span className="hidden sm:inline text-sm">Envoyer</span>
                  </>
                )}
              </button>

              <button type="button" className="p-2 rounded-lg hover:bg-slate-50" aria-label="Voix">
                <Mic size={18} />
              </button>
            </div>
            {error && (
              <div className="mt-2 text-xs text-rose-600 flex items-center gap-1">
                <AlertTriangle size={14} />
                <span>{error}</span>
              </div>
            )}

            <div className="mt-3 flex gap-2 text-xs flex-wrap">
              {quickActions.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setInput((prev) => (prev ? `${prev} ${q}` : q))}
                  className="px-3 py-1 bg-slate-100 rounded-full hover:bg-slate-200"
                >
                  {q}
                </button>
              ))}
            </div>
          </form>
        </main>

        {/* Right column */}
        <aside className="col-span-3 bg-white/10 backdrop-blur-lg border border-white/10 rounded-2xl shadow-xl p-4 flex flex-col gap-4 overflow-hidden text-white">
          <div className="text-sm font-semibold text-white">Dernière réponse</div>

          <div className="rounded-lg border border-white/20 bg-white/5 p-3">
            {!lastResult ? (
              <p className="text-xs text-white/70">
                Lance une recherche pour afficher l'analyse, les articles cités et les métadonnées.
              </p>
            ) : (
              <>
                <div className="text-xs text-white/70 flex items-center justify-between">
                  <span>{formatTimestamp(lastResult.timestamp)}</span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[11px] ${
                      lastResult.mode === "offline"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-emerald-100 text-emerald-700"
                    }`}
                  >
                    {lastResult.mode === "offline" ? "Mode debug" : "En ligne"}
                  </span>
                </div>
                <div className="mt-2 text-sm font-semibold">
                  {lastResult.code || "Tous les codes disponibles"}
                </div>

                <div className="mt-3 grid gap-3">
                  {renderPositionCard("Position favorable", proPosition, "text-emerald-600")}
                  {renderPositionCard("Position contraire", contraPosition, "text-rose-600")}
                </div>

                {vigilancePoints.length > 0 && (
                  <div className="mt-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-800">
                    <div className="font-semibold">Points de vigilance</div>
                    <ul className="list-disc pl-4 space-y-1 mt-1">
                      {vigilancePoints.map((pt, idx) => (
                        <li key={`vigilance-${idx}`}>{pt}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="mt-3">
                  <div className="text-xs uppercase tracking-wide text-white/70">Synthèse</div>
                  <div className="mt-2 rounded-xl bg-white/10 p-3 text-xs text-white whitespace-pre-wrap">
                    {analysisObject?.synthese ||
                      (typeof lastResult.analysis === "string"
                        ? lastResult.analysis
                        : lastResult.answer)}
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="rounded-lg border border-slate-100 p-3 flex flex-col gap-2 overflow-auto">
            <div className="text-xs text-slate-500">Articles cités</div>
            {!lastResult || !lastResult.articles?.length ? (
              <p className="text-xs text-slate-500">Aucun article pour le moment.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {lastResult.articles.map((article) => (
                  <div key={article.id} className="rounded-lg bg-slate-50 p-2">
                    <div className="text-xs font-semibold text-slate-700">{article.title}</div>
                    <div className="text-[11px] text-slate-500">{article.code}</div>
                    <p className="mt-1 text-xs text-slate-600 line-clamp-3">{article.excerpt}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-auto flex gap-2">
            <button className="flex-1 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold">
              Exporter l'analyse
            </button>
            <button className="py-2 px-3 rounded-lg border border-slate-200">Partager</button>
          </div>
        </aside>
      </div>
    </div>
  );
}
