import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Send,
  Paperclip,
  Settings,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  User,
  ChevronDown,
  BookOpen,
  ArrowLeft, 
  Clock, 
  FileText
} from "lucide-react";
import ReactMarkdown from 'react-markdown'
const CraftLogoNew = "/assets/image_3.png"; 

const quickActions = ["Résumé", "Priorités", "Export PDF"];

const initialMessages = [
  {
    id: 1,
    who: "bot",
    text: "⚠️ Cet assistant peut se tromper. Les réponses fournies ne constituent pas un avis juridique. Pour toute situation importante, veuillez consulter un professionnel du droit.",
    time: formatTime(),
  },
  {
    id: 2,
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

// --- HEADER PLATEFORME ---
function Header() {
  return (
    <header className="bg-[#050b2a] px-6 flex items-center justify-between border-b border-white/10 sticky top-0 z-10 h-14 shadow-md">
      <div className="flex items-center gap-3">
        <img src={CraftLogoNew} alt="Craft.AI" className="h-10" />
      </div>
      <div className="flex items-center gap-3">
        <button className="p-2 rounded-lg hover:bg-white/10 text-white/70 hover:text-white transition-colors" title="Documentation">
            <BookOpen size={20} />
        </button>
        <button className="flex items-center gap-1 p-1 pr-2 rounded-full hover:bg-white/10 transition-colors group">
           <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#4F46E5] to-[#818cf8] flex items-center justify-center text-white shadow-sm border border-white/10 group-hover:border-white/30">
             <User size={16} />
           </div>
           <ChevronDown size={14} className="text-white/40 group-hover:text-white/80 transition-colors"/>
        </button>
      </div>
    </header>
  );
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
  
  // --- NOUVEAU STATE POUR L'HISTORIQUE ---
  const [history, setHistory] = useState([]); // Liste de toutes les analyses
  const [activeResult, setActiveResult] = useState(null); // L'analyse qu'on est en train de regarder (Détail)

  const messagesEndRef = useRef(null);

  useEffect(() => scrollToBottom(), [messages, loading]);
  
  useEffect(() => {
    bootstrap();
  }, []);

  const filteredCodes = codes.filter((code) =>
    code.label.toLowerCase().includes(query.toLowerCase())
  );

  // Helper pour extraire les données de l'analyse active
  const analysisObject =
    activeResult && typeof activeResult.analysis === "object" ? activeResult.analysis : null;
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

  const renderPositionCard = (label, data, accentColor) => {
    if (!data || data === "INFORMATION_INSUFFISANTE") {
      return (
        <div key={label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className={`text-sm font-semibold ${accentColor}`}>{label}</div>
          <p className="text-sm text-slate-500 mt-1">Information insuffisante.</p>
        </div>
      );
    }

    return (
      <div key={label} className="rounded-xl border border-slate-200 bg-white p-4 space-y-3 shadow-sm">
        <div className={`text-sm font-semibold ${accentColor}`}>{label}</div>
        <div className="text-base font-medium text-[#0F1F53]">{data.these}</div>
        <div className="text-sm text-slate-500">
          <span className="font-medium">Textes cités : </span>
          {Array.isArray(data.textes_applicables) && data.textes_applicables.length > 0
            ? data.textes_applicables.join(", ")
            : "—"}
        </div>
        <div className="text-sm text-[#0F1F53] space-y-3">
          {Array.isArray(data.arguments) && data.arguments.length > 0 ? (
            data.arguments.map((arg, idx) => (
              <div key={`${label}-${idx}`}>
                <div className="font-semibold">{arg.point || `Argument ${idx + 1}`}</div>
                <p className="whitespace-pre-wrap text-slate-700">{arg.analyse}</p>
                {Array.isArray(arg.sources) && arg.sources.length > 0 && (
                  <div className="text-xs text-slate-400 mt-1">{arg.sources.join(", ")}</div>
                )}
              </div>
            ))
          ) : (
            <p>Aucun argument détaillé.</p>
          )}
        </div>
        {Array.isArray(data.risques) && data.risques.length > 0 && (
          <div className="text-sm text-amber-700 bg-amber-50 p-2 rounded-md border border-amber-200">
            <span className="font-semibold">Risques :</span> {data.risques.join("; ")}
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

      const replyText = cleanedAnswer;
      const reply = {
        id: Date.now() + 1,
        who: "bot",
        text: replyText,
        time: formatTime(),
    };
      setMessages((prev) => [...prev, reply]);

      // --- MISE À JOUR HISTORIQUE ---
      const newResult = {
        ...payload,
        answer: cleanedAnswer,
        analysis: normalizedAnalysis,
        id: Date.now(), 
        original_question: text 
      };

      setHistory(prev => [newResult, ...prev]); 
      setActiveResult(newResult); 

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
const exportToPDF = () => {
  const printWindow = window.open('', '_blank');
  
  // On récupère le texte de la réponse complète
  const mainAnalysis = activeResult.answer; 
  
  // On génère la liste des articles cités s'ils existent
  const articlesHtml = activeResult.articles?.map(art => `
    <div style="margin-bottom: 15px; padding: 10px; border-left: 3px solid #4F46E5; background: #f1f5f9;">
      <strong>${art.title}</strong> (${art.code})<br>
      <small>${art.excerpt}</small>
    </div>
  `).join('') || "Aucun article cité.";

  printWindow.document.write(`
    <html>
      <head>
        <title>Rapport Juridique - Craft.AI</title>
        <style>
          body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 50px; color: #1e293b; line-height: 1.5; }
          .header { border-bottom: 2px solid #4F46E5; margin-bottom: 30px; padding-bottom: 20px; }
          h1 { color: #0F1F53; margin: 0; }
          .question-box { background: #f8fafc; padding: 15px; border-radius: 8px; margin-bottom: 30px; font-style: italic; border: 1px solid #e2e8f0; }
          .section-title { color: #4F46E5; text-transform: uppercase; font-size: 0.9rem; font-weight: bold; margin-top: 30px; margin-bottom: 10px; }
          .main-content { white-space: pre-wrap; background: white; }
          .footer { margin-top: 50px; font-size: 0.7rem; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 20px; }
        </style>
      </head>
      <body>
        <div class="header">
          <h1>Analyse Juridique</h1>
          <p>Généré par Craft.AI Legal le ${new Date().toLocaleDateString('fr-FR')}</p>
        </div>

        <div class="section-title">Question posée</div>
        <div class="question-box">"${activeResult.original_question}"</div>

        <div class="section-title">Analyse et Recommandations</div>
        <div class="main-content">${mainAnalysis}</div>

        <div class="section-title">Sources (LegiFrance)</div>
        <div class="articles-list">${articlesHtml}</div>

        <div class="footer">
          Document généré à titre informatif. Ne remplace pas la consultation d'un avocat.
        </div>
      </body>
    </html>
  `);
  
  printWindow.document.close();
  // Petit délai pour laisser le temps au navigateur de préparer le rendu
  setTimeout(() => {
    printWindow.print();
  }, 500);
};
  return (
    <div className="h-screen w-full bg-[#FAF9F7] flex flex-col font-sans">
      <Header />
      <div className="flex-1 w-full grid grid-cols-12 gap-6 px-8 py-6 overflow-hidden">

        {/* --- COLONNE DE GAUCHE : FILTRES --- */}
        <aside className="col-span-3 bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex flex-col gap-6 overflow-hidden">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-lg font-bold text-[#0F1F53]">CRAFT.AI LEGAL</div>
              <div className="text-sm text-slate-500 flex items-center gap-1.5 mt-1">
                {backendStatus === "offline" ? (
                  <>
                    <AlertTriangle size={14} className="text-rose-500" />
                    <span>Serveur hors-ligne</span>
                  </>
                ) : backendStatus === "checking" ? (
                  <>
                    <Loader2 size={14} className="animate-spin text-amber-500" />
                    <span>Connexion...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={14} className="text-emerald-500" />
                    <span>Connecté</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <label className="relative block">
            <span className="sr-only">Recherche de code</span>
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
              <Search size={18} />
            </span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="block w-full bg-slate-100 text-[#0F1F53] placeholder:text-slate-400 border border-transparent rounded-xl py-3 pl-10 pr-4 focus:outline-none focus:bg-white focus:border-[#4F46E5] focus:ring-1 focus:ring-[#4F46E5] transition-all"
              placeholder="Rechercher un code..."
            />
          </label>

          <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-slate-200 pr-2">
            <ul className="flex flex-col gap-3">
              {filteredCodes.length === 0 && (
                <li className="text-sm text-slate-500 px-2">Aucun code trouvé.</li>
              )}
              {filteredCodes.map((code) => (
                <li
                  key={code.id}
                  onClick={() => toggleCodeSelection(code)}
                  className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer border transition-all ${
                    selectedCode?.id === code.id
                      ? "border-[#4F46E5] bg-[#4F46E5]/10"
                      : "border-slate-200 hover:border-[#4F46E5]/50 hover:bg-slate-50"
                  }`}
                >
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-sm font-semibold ${selectedCode?.id === code.id ? 'bg-[#4F46E5] text-white' : 'bg-slate-100 text-slate-500'}`}>
                    {code.label.substring(0, 2)}
                  </div>
                  <div className="flex-1">
                    <div className={`text-sm font-medium ${selectedCode?.id === code.id ? 'text-[#4F46E5]' : 'text-[#0F1F53]'}`}>{code.label}</div>
                    {selectedCode?.id === code.id && (
                      <div className="text-xs text-[#4F46E5]/80">Filtre actif</div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <button
            onClick={() => setSelectedCode(null)}
            className="w-full py-3 rounded-xl bg-[#0F1F53] text-white text-sm font-semibold hover:bg-[#0F1F53]/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={!selectedCode}
          >
            Tous les codes
          </button>
        </aside>

        {/* --- COLONNE CENTRALE : CHAT --- */}
        <main className="col-span-6 bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex flex-col overflow-hidden relative">
          <header className="flex items-center justify-between pb-4 border-b border-slate-200">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#4F46E5] to-[#818cf8] flex items-center justify-center text-white font-bold text-lg shadow-sm">
                AJ
              </div>
              <div>
                <div className="text-base font-bold text-[#0F1F53]">Assistant juridique</div>
                <div className="text-sm text-slate-500 flex items-center gap-2">
                    {backendStatus === "offline" ? (
                        <span className="flex items-center gap-1 text-rose-500"><AlertTriangle size={12}/> Hors-ligne</span>
                    ) : (
                        <span className="flex items-center gap-1 text-emerald-600"><span className="w-2 h-2 rounded-full bg-emerald-500"/> Connecté</span>
                    )}
                </div>
              </div>
            </div>
            <div className="text-xs font-medium text-slate-400 bg-slate-50 px-3 py-1 rounded-full border border-slate-200">
               {selectedCode ? selectedCode.label : "Tous les codes"}
            </div>
          </header>

          <section className="flex-1 overflow-auto py-6 px-2" aria-live="polite">
            <ul className="flex flex-col gap-6">
              <AnimatePresence initial={false} mode="popLayout">
                {messages.map((m) => (
                  <motion.li
                    key={m.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className={`flex ${m.who === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div className={`flex flex-col ${m.who === "user" ? "items-end" : "items-start"} max-w-[85%]`}>
                      <div
                        className={`p-4 shadow-sm ${
                          m.who === "user"
                            ? "bg-[#4F46E5] text-white rounded-2xl rounded-br-sm"
                            : "bg-slate-100 text-[#0F1F53] rounded-2xl rounded-tl-sm border border-slate-200"
                        }`}
                      >
                        <div className="text-base leading-relaxed markdown-container">
                          {m.who === "bot" ? (
                            <ReactMarkdown>{m.text}</ReactMarkdown>
                          ) : (
                            <div className="whitespace-pre-wrap">{m.text}</div>
                            )}
                      </div>
                      </div> 
                      <div className={`text-xs mt-1.5 font-medium ${m.who === "user" ? "text-slate-500" : "text-slate-400"}`}>
                        {m.time}
                      </div>
                    </div>
                  </motion.li>
                ))}
              </AnimatePresence>
              
              {loading && (
                  <motion.li
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex justify-start"
                  >
                    <div className="bg-slate-100 p-4 rounded-2xl rounded-tl-sm border border-slate-200 shadow-sm flex items-center gap-1">
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"></span>
                    </div>
                  </motion.li>
              )}
              <div ref={messagesEndRef} />
            </ul>
          </section>

          <form onSubmit={sendMessage} className="pt-4 border-t border-slate-200 relative bg-white">
             {error && (
              <div className="absolute -top-10 left-0 right-0 bg-rose-50 text-rose-600 px-4 py-2 rounded-lg text-sm flex items-center gap-2 border border-rose-200">
                <AlertTriangle size={16} />
                <span>{error}</span>
              </div>
            )}
            <div className="flex items-end gap-3">
              <div className="flex-1 relative">
                <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                        if(e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            sendMessage(e);
                        }
                    }}
                    placeholder="Posez votre question juridique..."
                    className="w-full bg-slate-100 border border-slate-200 rounded-2xl py-4 pl-5 pr-12 focus:outline-none focus:bg-white focus:border-[#4F46E5] focus:ring-1 focus:ring-[#4F46E5] text-[#0F1F53] placeholder:text-slate-400 resize-none min-h-[60px] max-h-[150px]"
                    rows={1}
                />
                <div className="absolute right-3 bottom-3 flex gap-2 text-slate-400">
                    <button type="button" className="p-1.5 rounded-lg hover:bg-slate-200 hover:text-[#0F1F53] transition-colors" aria-label="Attacher">
                        <Paperclip size={20} />
                    </button>
                </div>
              </div>

              <button
                type="submit"
                className="bg-[#4F46E5] hover:bg-[#4338ca] disabled:bg-[#4F46E5]/50 disabled:cursor-not-allowed text-white rounded-xl px-5 py-4 flex items-center justify-center gap-2 shadow-sm transition-colors h-[60px]"
                disabled={loading || !input.trim()}
              >
                <Send size={20} />
              </button>
            </div>

            <div className="mt-4 flex gap-2">
              {quickActions.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setInput((prev) => (prev ? `${prev} ${q}` : q))}
                  className="px-4 py-2 bg-white border border-slate-200 text-sm font-medium text-[#0F1F53] rounded-full hover:bg-slate-50 hover:border-[#4F46E5]/30 transition-all shadow-sm"
                >
                  {q}
                </button>
              ))}
            </div>
          </form>
        </main>

        {/* --- COLONNE DE DROITE : HISTORIQUE OU DÉTAILS --- */}
        <aside className="col-span-3 flex flex-col gap-6 overflow-hidden">
            
            {/* Cas 1 : Aucun résultat du tout (État initial) */}
            {history.length === 0 ? (
                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex-1 flex flex-col gap-6 overflow-hidden items-center justify-center text-center">
                    <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-2">
                        <Clock size={32} className="text-slate-300"/>
                    </div>
                    <p className="text-sm text-slate-500">
                        Votre historique de recherche apparaîtra ici.
                    </p>
                </div>
            ) : !activeResult ? (
                
                /* Cas 2 : LISTE DE L'HISTORIQUE (Quand on n'a pas cliqué sur un détail) */
                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex-1 flex flex-col gap-4 overflow-hidden">
                    <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                        <div className="text-lg font-bold text-[#0F1F53] flex items-center gap-2">
                            <Clock size={20}/> Historique
                        </div>
                        <span className="text-xs bg-slate-100 px-2 py-1 rounded-full text-slate-600">{history.length}</span>
                    </div>
                    
                    <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-slate-200 pr-2 space-y-3">
                        {history.map((item) => (
                            <div 
                                key={item.id} 
                                onClick={() => setActiveResult(item)}
                                className="p-4 rounded-xl border border-slate-100 bg-slate-50 hover:bg-white hover:border-[#4F46E5]/30 hover:shadow-md transition-all cursor-pointer group"
                            >
                                <div className="text-xs text-slate-400 mb-1 flex justify-between">
                                    <span>{formatTimestamp(item.timestamp)}</span>
                                    <span className="text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded text-[10px]">Succès</span>
                                </div>
                                <div className="text-sm font-semibold text-[#0F1F53] line-clamp-2 mb-2 group-hover:text-[#4F46E5] transition-colors">
                                    {item.original_question}
                                </div>
                                <div className="text-xs text-slate-500 line-clamp-2">
                                    {item.analysis?.synthese || item.answer}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

            ) : (

                /* Cas 3 : VUE DÉTAILLÉE (L'analyse complète) */
                <>
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex-1 flex flex-col gap-6 overflow-hidden">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <button 
                                    onClick={() => setActiveResult(null)}
                                    className="p-1 rounded-full hover:bg-slate-100 text-slate-400 hover:text-[#0F1F53] transition-colors"
                                    title="Retour à l'historique"
                                >
                                    <ArrowLeft size={20} />
                                </button>
                                <div className="text-lg font-bold text-[#0F1F53]">Analyse</div>
                            </div>
                            
                            <span className={`px-3 py-1 rounded-full text-xs font-medium flex items-center gap-1.5 ${activeResult.mode === "offline" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                                <span className={`inline-block w-1.5 h-1.5 rounded-full ${activeResult.mode === "offline" ? "bg-amber-500" : "bg-emerald-500"}`}></span>
                                {activeResult.mode === "offline" ? "Debug" : "Live"}
                            </span>
                        </div>

                        <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-slate-200 pr-2 flex flex-col gap-6">
                            <div className="text-xs text-slate-500 font-medium uppercase tracking-wider">
                                {formatTimestamp(activeResult.timestamp)} • {activeResult.code || "Tous les codes"}
                            </div>

                            {/* Résumé de la question pour contexte */}
                            <div className="bg-slate-50 p-3 rounded-lg border border-slate-100 text-sm text-[#0F1F53] italic">
                                "{activeResult.original_question}"
                            </div>

                            {vigilancePoints.length > 0 && (
                            <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 shadow-sm">
                                <div className="text-sm font-semibold text-amber-800 flex items-center gap-2">
                                    <AlertTriangle size={16} /> Points de vigilance
                                </div>
                                <ul className="list-disc pl-5 space-y-1 mt-2 text-sm text-amber-700">
                                {vigilancePoints.map((pt, idx) => (
                                    <li key={`vigilance-${idx}`}>{pt}</li>
                                ))}
                                </ul>
                            </div>
                            )}

                            <div className="rounded-xl bg-[#0F1F53] p-5 text-white shadow-sm">
                                <div className="text-xs font-bold uppercase tracking-wider opacity-80 mb-3">Synthèse</div>
                                <div className="text-sm leading-relaxed whitespace-pre-wrap">
                                    {analysisObject?.synthese ||
                                    (typeof activeResult.analysis === "string"
                                        ? activeResult.analysis
                                        : activeResult.answer)}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 max-h-[300px] flex flex-col gap-4 overflow-hidden">
                        <div className="text-base font-bold text-[#0F1F53]">Articles cités</div>
                        {!activeResult.articles?.length ? (
                            <p className="text-sm text-slate-500 py-4">Aucun article cité pour le moment.</p>
                        ) : (
                            <div className="flex-1 overflow-auto scrollbar-thin scrollbar-thumb-slate-200 pr-2 flex flex-col gap-3">
                            {activeResult.articles.map((article) => (
                                <div key={article.id} className="rounded-xl bg-slate-50 border border-slate-200 p-4 hover:bg-slate-100 hover:border-slate-300 transition-all">
                                <div className="text-sm font-bold text-[#0F1F53] mb-1">{article.title}</div>
                                <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">{article.code}</div>
                                <p className="text-sm text-slate-600 line-clamp-3 leading-relaxed">{article.excerpt}</p>
                                </div>
                            ))}
                            </div>
                        )}
                    </div>

                    <div className="flex gap-3">
                        <button 
                        onClick={exportToPDF}
                        className="flex-1 py-3 rounded-xl bg-[#4F46E5] hover:bg-[#4338ca] text-white text-sm font-semibold shadow-sm transition-colors">
                            Exporter
                        </button>
                        <button className="py-3 px-6 rounded-xl bg-white border border-slate-200 text-[#0F1F53] text-sm font-semibold hover:bg-slate-50 hover:border-slate-300 transition-colors">
                            Partager
                        </button>
                    </div>
                </>
            )}
        </aside>
      </div>
    </div>
  );
}