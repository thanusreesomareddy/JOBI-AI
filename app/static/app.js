const API = "";

const state = {
  candidateId: localStorage.getItem("jobi_candidate_id") || null,
  resumeId: localStorage.getItem("jobi_resume_id") || null,
  plan: null,
  sessionId: null,
  nextPrompt: null,
  sessionStatus: null,
  progress: null,
  selectedDay: null,
  serverStt: false,
  sttProvider: "none",
  speakMethod: "browser",
  ttsEnabled: localStorage.getItem("jobi_tts_enabled") !== "false",
  ttsVoiceUri: localStorage.getItem("jobi_tts_voice") || "",
  adaptPlanEnabled: localStorage.getItem("jobi_adapt_plan") !== "false",
  sessionStart: null,
  interviewBusy: false,
  interviewJoined: false,
  joinInProgress: false,
  interviewPaused: false,
  interviewPhase: "lobby",
  interviewRoundIndex: 0,
  lastTopicSubmitConfirmed: false,
  feedbackAnswers: [],
  lastSessionResult: null,
  feedbackTotalRounds: 4,
  coachSpeaking: false,
  bargeInActive: false,
  voicePhase: "idle",
};

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
const browserSttSupported = !!SpeechRecognitionCtor;
const browserTtsSupported = "speechSynthesis" in window;

const $ = (id) => document.getElementById(id);

function setStep(n) {
  document.querySelectorAll(".step").forEach((el, i) => {
    el.classList.remove("active", "done");
    if (i + 1 < n) el.classList.add("done");
    if (i + 1 === n) el.classList.add("active");
  });
}

function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(id).classList.add("active");
}

function showError(el, msg) {
  el.textContent = msg;
  el.hidden = !msg;
}

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  let data = null;
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail) || res.statusText;
    throw new Error(msg);
  }
  return data;
}

function saveIds() {
  if (state.candidateId) localStorage.setItem("jobi_candidate_id", state.candidateId);
  if (state.resumeId) localStorage.setItem("jobi_resume_id", state.resumeId);
}

function clearStorage() {
  localStorage.removeItem("jobi_candidate_id");
  localStorage.removeItem("jobi_resume_id");
  state.candidateId = null;
  state.resumeId = null;
  state.plan = null;
  state.sessionId = null;
}

function scoreTier(score) {
  if (score == null) return "";
  if (score >= 8) return "score-high";
  if (score >= 5) return "score-mid";
  return "score-low";
}

function selectDay(dayNum) {
  state.selectedDay = dayNum;
  $("day-select").value = String(dayNum);
  document.querySelectorAll(".day-card").forEach((card) => {
    card.classList.toggle("selected", Number(card.dataset.day) === dayNum);
  });
  updateStartDayButton();
}

function updateStartDayButton() {
  const btn = $("btn-start-day");
  if (!btn || !state.selectedDay) return;
  const p = (state.progress?.days || []).find((d) => d.day === state.selectedDay);
  if (p?.status === "completed") {
    btn.textContent = p.attempts > 1 ? `Practice again · ${p.attempts} tries` : "Practice again";
  } else if (p?.status === "in_progress") {
    btn.textContent = "Start day";
  } else {
    btn.textContent = "Start day";
  }
}

function renderFocusAreas() {
  const viewBtn = $("btn-view-focus");
  const areas = state.progress?.focus_areas || [];
  if (viewBtn) {
    viewBtn.hidden = areas.length === 0;
  }
}

function showFocusAreasScreen() {
  const list = $("focus-areas-list");
  const empty = $("focus-empty");
  const areas = state.progress?.focus_areas || [];

  list.innerHTML = "";
  if (!areas.length) {
    empty.hidden = false;
    list.hidden = true;
  } else {
    empty.hidden = true;
    list.hidden = false;
    areas.forEach((area) => {
      const li = document.createElement("li");
      const count = area.mentions;
      const label = count === 1 ? "1 mention" : `${count} mentions`;
      li.innerHTML = `
        <span class="focus-area-text">${area.topic}</span>
        <span class="focus-area-count" title="Flagged ${count} time(s) in your session feedback">${label}</span>
      `;
      list.appendChild(li);
    });
  }
  showScreen("screen-focus");
}

function renderPlanDays() {
  const select = $("day-select");
  const cards = $("day-cards");
  select.innerHTML = "";
  cards.innerHTML = "";

  const schedule = state.plan?.plan?.schedule || state.plan?.schedule || [];
  const progressMap = Object.fromEntries((state.progress?.days || []).map((d) => [d.day, d]));

  schedule.forEach((day, index) => {
    const p = progressMap[day.day];
    const status = p?.status || "not_started";
    const score = p?.average_score ?? null;

    const opt = document.createElement("option");
    opt.value = day.day;
    opt.textContent = `Day ${day.day}`;
    select.appendChild(opt);

    const card = document.createElement("button");
    card.type = "button";
    card.className = "day-card";
    card.dataset.day = day.day;
    if (status === "completed") card.classList.add("done");
    if (status === "in_progress") card.classList.add("active");

    const barPct = score != null ? Math.min(100, (score / 10) * 100) : status === "in_progress" ? 35 : 0;
    const barTier = scoreTier(score);
    const scoreDisplay = score != null ? score.toFixed(1) : "—";
    const personalized = p?.personalized || day.personalized;
    if (personalized) card.classList.add("personalized");
    let statusLabel =
      status === "completed" ? "Done" : status === "in_progress" ? "In progress" : "Not started";
    if (status === "completed" && p?.attempts > 1) {
      statusLabel = `Done · ${p.attempts}×`;
    }
    if (status === "completed" && p?.best_score != null && p.best_score !== score) {
      statusLabel += ` · best ${Number(p.best_score).toFixed(1)}`;
    }
    const badge = personalized
      ? `<span class="day-card-badge">✨ Personalized</span>`
      : "";

    card.innerHTML = `
      <div class="day-card-num">D${day.day}</div>
      <div class="day-card-body">
        ${badge}
        <p class="day-card-title">${day.title}</p>
        <div class="day-card-bar-wrap">
          <div class="day-card-bar ${barTier}" style="width: ${barPct}%"></div>
        </div>
      </div>
      <div class="day-card-meta">
        <div class="day-card-score ${barTier}">${scoreDisplay}</div>
        <div class="day-card-status ${status}">${statusLabel}</div>
      </div>
    `;

    card.addEventListener("click", () => selectDay(day.day));
    cards.appendChild(card);

    if (index === 0 && !state.selectedDay) {
      selectDay(day.day);
    }
  });

  if (state.selectedDay) {
    selectDay(state.selectedDay);
  } else {
    updateStartDayButton();
  }
  renderFocusAreas();
}

async function loadProgress() {
  if (!state.candidateId) return;
  try {
    state.progress = await api(`/progress/candidate/${state.candidateId}`);
    renderPlanDays();
  } catch {
    state.progress = null;
  }
}

async function loadPlan() {
  if (!state.candidateId) return;
  try {
    const row = await api(`/plans/candidate/${state.candidateId}`);
    state.plan = { plan: row.plan, candidate_id: row.candidate_id, plan_id: row.plan_id };
  } catch {
    /* keep existing plan */
  }
}

async function refreshPlanScreen() {
  await Promise.all([loadPlan(), loadProgress()]);
}

function setProcessingItem(id, status) {
  const el = $(id);
  el.classList.remove("done", "active");
  if (status === "done") el.classList.add("done");
  if (status === "active") el.classList.add("active");
}

async function runPipeline(file) {
  setStep(2);
  showScreen("screen-processing");
  showError($("processing-error"), "");
  setProcessingItem("proc-upload", "done");
  setProcessingItem("proc-analyze", "active");
  setProcessingItem("proc-plan", "");

  const form = new FormData();
  form.append("file", file);

  const upload = await api("/resume/upload", { method: "POST", body: form });
  state.candidateId = upload.candidate_id;
  state.resumeId = upload.resume_id;
  saveIds();

  setProcessingItem("proc-analyze", "active");
  await api(`/resume/${state.resumeId}/analyze`, { method: "POST" });
  setProcessingItem("proc-analyze", "done");
  setProcessingItem("proc-plan", "active");

  const generated = await api(`/plans/generate?resume_id=${state.resumeId}`, { method: "POST" });
  state.plan = generated;
  setProcessingItem("proc-plan", "done");
  $("spinner").hidden = true;

  await showPlanReady();
}

function syncAdaptPlanOption() {
  const checkbox = $("opt-adapt-plan");
  if (!checkbox) return;
  checkbox.checked = state.adaptPlanEnabled;
}

function saveAdaptPlanPreference() {
  const checkbox = $("opt-adapt-plan");
  if (!checkbox) return;
  state.adaptPlanEnabled = checkbox.checked;
  localStorage.setItem("jobi_adapt_plan", String(state.adaptPlanEnabled));
}

async function showPlanReady() {
  setStep(2);
  showScreen("screen-plan");
  const role = state.plan?.plan?.target_role || state.progress?.target_role || "Your role";
  $("plan-role").textContent = `Training for: ${role}`;
  const days = state.plan?.plan?.days || state.progress?.total_days || 7;
  $("plan-summary").textContent = `Your ${days}-day plan is ready. Tap a day below, then start practice.`;
  state.selectedDay = null;
  syncAdaptPlanOption();
  renderPlanDays();
  await loadProgress();
}

let speechRecognition = null;
let browserTranscript = "";
let browserInterim = "";
let browserListeningActive = false;
let micStream = null;
let silenceSubmitTimer = null;
let coachSpeakCallback = null;
let coachMessageLines = [];
let coachMessageIndex = 0;
const SILENCE_SUBMIT_MS = 1200;
const RESUME_MIC_DELAY_MS = 200;
const MIN_SPEECH_CHARS = 4;

const INTERVIEWER = {
  male: { name: "Alex", image: "/static/img/interviewer-male.png" },
  female: { name: "Sarah", image: "/static/img/interviewer-female.png" },
};

function isChromeOrEdge() {
  const ua = navigator.userAgent;
  return (ua.includes("Chrome") || ua.includes("Edg")) && !ua.includes("Firefox");
}

function getEnglishVoices() {
  if (!browserTtsSupported) return [];
  return speechSynthesis
    .getVoices()
    .filter((v) => v.lang.toLowerCase().startsWith("en"))
    .sort((a, b) => {
      if (a.localService !== b.localService) return a.localService ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
}

function getCoachVoice() {
  const voices = getEnglishVoices();
  if (!voices.length) return null;
  const saved = state.ttsVoiceUri || localStorage.getItem("jobi_tts_voice");
  return voices.find((v) => v.voiceURI === saved) || voices[0];
}

function getVoiceGender(voice) {
  if (!voice) return "male";
  const name = voice.name.toLowerCase();
  if (/female|jenny|aria|zira|samantha|victoria|susan|hazel|linda|heather|emma|michelle|sara|sonia|natasha|laura|lisa|karen|anna|alice|emma|olivia|ava|emma/i.test(name)) {
    return "female";
  }
  if (/male|guy|david|mark|james|ryan|george|brian|eric|steven|paul|andrew|thomas|daniel|christopher/i.test(name)) {
    return "male";
  }
  return "male";
}

function updateInterviewerAvatar() {
  const voice = getCoachVoice();
  const gender = getVoiceGender(voice);
  const profile = INTERVIEWER[gender] || INTERVIEWER.male;
  const img = $("interviewer-avatar");
  const nameEl = $("interviewer-name");
  if (img) img.src = profile.image;
  if (nameEl) nameEl.textContent = profile.name;
  state.interviewerName = profile.name;
}

function setAvatarState(avatarState) {
  const wrap = $("interviewer-avatar-wrap");
  if (wrap) wrap.dataset.state = avatarState || "idle";
}

let avatarReactionTimer = null;

function clearAvatarReaction() {
  if (avatarReactionTimer) {
    clearTimeout(avatarReactionTimer);
    avatarReactionTimer = null;
  }
  const wrap = $("interviewer-avatar-wrap");
  if (wrap) delete wrap.dataset.reaction;
}

function playAvatarReaction(score) {
  const wrap = $("interviewer-avatar-wrap");
  if (!wrap || score == null || Number.isNaN(Number(score))) return;

  clearAvatarReaction();

  let reaction = "coaching";
  if (score >= 8) reaction = "encouraged";
  else if (score >= 5) reaction = "supportive";

  wrap.dataset.reaction = reaction;
  avatarReactionTimer = setTimeout(() => {
    delete wrap.dataset.reaction;
    avatarReactionTimer = null;
  }, 2000);
}

function populateVoiceSelect() {
  const select = $("tts-voice-select");
  if (!select) return;

  const voices = getEnglishVoices();
  const previous = state.ttsVoiceUri || select.value;

  select.innerHTML = "";
  voices.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v.voiceURI;
    const tag = v.localService ? "" : " · online";
    opt.textContent = `${v.name}${tag}`;
    select.appendChild(opt);
  });

  if (!voices.length) {
    select.hidden = true;
    return;
  }

  const preferred =
    voices.find((v) => v.voiceURI === previous) ||
    voices.find((v) => /google|natural|zira|aria|jenny|guy/i.test(v.name)) ||
    voices[0];

  select.value = preferred.voiceURI;
  state.ttsVoiceUri = preferred.voiceURI;
  localStorage.setItem("jobi_tts_voice", preferred.voiceURI);
  updateInterviewerAvatar();
}

function previewCoachVoice() {
  speakCoach("Hi, I'm your practice coach.", { force: true });
}

function stopCoachSpeech() {
  if (!browserTtsSupported) return;
  speechSynthesis.cancel();
  state.coachSpeaking = false;
}

function textForSpeech(text) {
  if (!text) return "";
  return text
    .replace(/[\u{1F000}-\u{1FFFF}]/gu, "")
    .replace(/[\u{2600}-\u{27BF}]/gu, "")
    .replace(/[\u{FE00}-\u{FE0F}]/gu, "")
    .replace(/[\u{200D}]/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

function speakCoach(text, { force = false, onEnd } = {}) {
  if ((!state.ttsEnabled && !force) || !browserTtsSupported || !text?.trim()) {
    state.coachSpeaking = false;
    onEnd?.();
    return;
  }
  const spoken = textForSpeech(text);
  if (!spoken) {
    state.coachSpeaking = false;
    onEnd?.();
    return;
  }
  stopCoachSpeech();
  state.coachSpeaking = true;
  const utterance = new SpeechSynthesisUtterance(spoken);
  const voice = getCoachVoice();
  if (voice) utterance.voice = voice;
  utterance.rate = 0.95;
  const finish = () => {
    state.coachSpeaking = false;
    if (!state.bargeInActive) onEnd?.();
  };
  utterance.onend = finish;
  utterance.onerror = finish;
  speechSynthesis.speak(utterance);
}

function speakNextCoachMessage() {
  if (state.bargeInActive || coachMessageIndex >= coachMessageLines.length) {
    state.coachSpeaking = false;
    const done = coachSpeakCallback;
    coachSpeakCallback = null;
    done?.();
    return;
  }
  const line = coachMessageLines[coachMessageIndex];
  coachMessageIndex += 1;
  speakCoach(line, { onEnd: speakNextCoachMessage });
}

function speakCoachMessages(messages, onDone) {
  coachMessageLines = (messages || []).filter((m) => m?.trim());
  coachMessageIndex = 0;
  coachSpeakCallback = onDone || null;
  state.bargeInActive = false;

  // Pause mic while interviewer speaks so speakers don't feed back into STT.
  stopContinuousListening();
  resetSpeechBuffers();
  const live = $("live-transcript");
  if (live) live.hidden = true;

  if (!state.ttsEnabled || !coachMessageLines.length) {
    state.coachSpeaking = false;
    onDone?.();
    return;
  }

  updateVoicePhase("coach-speaking");
  setAvatarState("speaking");
  updateVoicePhaseLabel("");
  setInterviewStatus(`${interviewerStatusPrefix()} is speaking…`);
  speakNextCoachMessage();
}

async function resumeListeningAfterCoach() {
  await new Promise((r) => setTimeout(r, RESUME_MIC_DELAY_MS));
  if (!state.interviewJoined || state.interviewBusy || state.coachSpeaking || state.interviewPaused) return;
  if (state.speakMethod !== "browser") return;
  await startContinuousListening();
}

function updateTtsControls() {
  const toggle = $("btn-tts-toggle");
  const voiceSelect = $("tts-voice-select");
  if (!toggle) return;

  if (!browserTtsSupported) {
    toggle.disabled = true;
    toggle.classList.remove("on");
    toggle.textContent = "🔇 Voice unavailable";
    if (voiceSelect) voiceSelect.hidden = true;
    return;
  }

  toggle.disabled = false;
  toggle.classList.toggle("on", state.ttsEnabled);
  toggle.textContent = state.ttsEnabled ? "🔊 Voice on" : "🔇 Voice off";
  if (voiceSelect) {
    voiceSelect.hidden = !state.ttsEnabled || getEnglishVoices().length === 0;
    voiceSelect.disabled = !state.ttsEnabled;
  }
}

function toggleCoachSpeech() {
  if (!browserTtsSupported) return;
  state.ttsEnabled = !state.ttsEnabled;
  localStorage.setItem("jobi_tts_enabled", String(state.ttsEnabled));
  if (!state.ttsEnabled) stopCoachSpeech();
  updateTtsControls();
}

function onVoicesReady() {
  populateVoiceSelect();
  updateTtsControls();
}

if (browserTtsSupported) {
  speechSynthesis.onvoiceschanged = onVoicesReady;
  onVoicesReady();
}

function resolveSpeakMethod() {
  if (state.sttProvider === "browser" || state.forceBrowserStt) return browserSttSupported ? "browser" : "none";
  if (state.serverStt) return "server";
  if (browserSttSupported) return "browser";
  return "none";
}

function updateSpeakHint() {
  state.speakMethod = resolveSpeakMethod();
  const hint = $("speak-hint");
  const panel = $("voice-assistant-panel");
  if (!hint) return;

  if (!browserSttSupported && state.speakMethod !== "server") {
    hint.textContent = "Live voice needs Chrome or Edge. Type your response below.";
    if (panel) panel.hidden = true;
    return;
  }

  if (!isChromeOrEdge() && state.speakMethod === "browser") {
    hint.textContent = "For hands-free voice, use Chrome or Edge — or type below.";
    if (panel) panel.hidden = true;
    return;
  }

  if (panel) panel.hidden = false;
  hint.textContent = state.interviewJoined
    ? "Speak when the interviewer finishes — pause briefly when you're done."
    : "Tap Join interview to meet your interviewer, then speak naturally.";
}

function releaseMic() {
  if (micStream) {
    micStream.getTracks().forEach((t) => t.stop());
    micStream = null;
  }
}

function getBrowserTranscriptText() {
  return `${browserTranscript} ${browserInterim}`.replace(/\s+/g, " ").trim();
}

function resetSpeechBuffers() {
  browserTranscript = "";
  browserInterim = "";
}

function clearSilenceSubmitTimer() {
  if (silenceSubmitTimer) {
    clearTimeout(silenceSubmitTimer);
    silenceSubmitTimer = null;
  }
}

function updateVoicePhase(phase) {
  state.voicePhase = phase;
  const orb = $("voice-orb");
  if (orb) orb.dataset.phase = phase;
  const heroStatus = $("interview-status");
  if (heroStatus) heroStatus.dataset.phase = phase;
  if (phase === "coach-speaking") setAvatarState("speaking");
  else if (phase === "listening") setAvatarState("listening");
  else if (phase === "thinking") setAvatarState("thinking");
  else if (phase === "complete") setAvatarState("idle");
}

function updateTopicProgress(label, roundIndex = 0, totalRounds = 0) {
  const bar = $("interview-progress-bar");
  const labelEl = $("question-progress");
  if (labelEl) labelEl.textContent = label;
  if (!bar) return;
  if (!totalRounds || label === "Ready to begin" || label === "Getting started") {
    bar.style.width = label === "Getting started" ? "8%" : "0%";
    return;
  }
  if (label === "Interview complete") {
    bar.style.width = "100%";
    return;
  }
  const pct = Math.round((roundIndex / totalRounds) * 100);
  bar.style.width = `${Math.min(100, Math.max(4, pct))}%`;
}

function interviewerStatusPrefix() {
  return state.interviewerName || "Interviewer";
}

function formatTopicPreviewShort(start) {
  const title = start?.title || state.sessionStart?.title;
  if (title) return `📋 Today: ${title}`;
  return "📋 Today’s practice session";
}

function feedbackScoreTier(score) {
  if (score >= 8) return "high";
  if (score >= 5) return "mid";
  return "low";
}

function renderFeedbackList(ul, items) {
  if (!ul) return;
  ul.innerHTML = "";
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  });
}

function resetFeedbackPanel(totalRounds = 4) {
  state.feedbackAnswers = [];
  state.feedbackTotalRounds = totalRounds || 4;
  $("feedback-empty").hidden = false;
  $("feedback-latest").hidden = true;
  $("feedback-history").innerHTML = "";
  $("feedback-final").hidden = true;
  $("feedback-sidebar")?.classList.remove("has-session-summary");
  updateFeedbackScoredLabel();
}

function updateFeedbackScoredLabel() {
  const el = $("feedback-scored-label");
  if (!el) return;
  const n = state.feedbackAnswers.length;
  el.textContent = n ? `${n} answer${n === 1 ? "" : "s"} reviewed` : "Waiting for your first answer";
}

function appendAnswerFeedback(evaluation, label) {
  if (!evaluation) return;
  state.feedbackAnswers.push({ label: label || "Your reply", evaluation });
  renderFeedbackPanel();
  playAvatarReaction(evaluation.score);
}

function hydrateTopicScoresFromTurns(turns, totalRounds) {
  if (!Array.isArray(turns) || !turns.length) return;
  state.feedbackTotalRounds = totalRounds || state.feedbackTotalRounds;
  state.feedbackAnswers = turns
    .map((turn, index) => ({
      label: `Topic ${(turn.prompt_index ?? index) + 1} complete`,
      evaluation: turn.evaluation,
    }))
    .filter((r) => r.evaluation && r.evaluation.score != null);
  renderFeedbackPanel();
}

function renderFeedbackPanel() {
  const answers = state.feedbackAnswers;
  const empty = $("feedback-empty");
  const latest = $("feedback-latest");
  const history = $("feedback-history");

  updateFeedbackScoredLabel();
  if (!answers.length) {
    if (empty) empty.hidden = false;
    if (latest) latest.hidden = true;
    if (history) history.innerHTML = "";
    return;
  }

  if (empty) empty.hidden = true;
  if (latest) latest.hidden = false;

  const current = answers[answers.length - 1];
  const ev = current.evaluation;
  const tier = feedbackScoreTier(ev.score);

  $("feedback-latest-topic").textContent = current.label;
  const ring = $("feedback-score-ring");
  if (ring) ring.dataset.tier = tier;
  $("feedback-score-value").textContent = ev.score;
  $("feedback-latest-text").textContent = ev.feedback;

  const strengthsBlock = $("feedback-strengths-block");
  const improvementsBlock = $("feedback-improvements-block");
  if (ev.strengths?.length) {
    strengthsBlock.hidden = false;
    renderFeedbackList($("feedback-strengths-list"), ev.strengths);
  } else if (strengthsBlock) {
    strengthsBlock.hidden = true;
  }
  if (ev.improvements?.length) {
    improvementsBlock.hidden = false;
    renderFeedbackList($("feedback-improvements-list"), ev.improvements);
  } else if (improvementsBlock) {
    improvementsBlock.hidden = true;
  }

  if (history) {
    history.innerHTML = "";
    if (answers.length > 1) {
      const title = document.createElement("p");
      title.className = "feedback-history-title";
      title.textContent = "Earlier answers";
      title.style.cssText = "margin:0 0 8px;font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted)";
      history.appendChild(title);
      answers.slice(0, -1).reverse().forEach((entry) => {
        const card = document.createElement("div");
        card.className = "feedback-history-card";
        card.dataset.tier = feedbackScoreTier(entry.evaluation.score);
        card.innerHTML = `<strong>${entry.label} · ${entry.evaluation.score}/10</strong><p class="feedback-history-snippet">${entry.evaluation.feedback}</p>`;
        history.appendChild(card);
      });
    }
  }
}

function showResultsPage(result) {
  clearInterviewCompleteUI();
  stopVoiceCapture();
  state.lastSessionResult = result;

  setStep(5);
  showScreen("screen-results");

  const day = state.sessionStart?.day;
  const title = state.sessionStart?.title || "Practice session";
  $("results-day-label").textContent = day ? `Day ${day}` : "Practice";
  $("results-title").textContent = title;

  const summary = result?.session_summary || {};
  const avg = summary.average_score ?? 0;
  const ring = $("results-score-ring");
  if (ring) ring.dataset.tier = feedbackScoreTier(Math.round(avg));
  $("results-avg-score").textContent = avg;
  $("results-headline").textContent = summary.headline || "Session complete";
  $("results-recommendation").textContent =
    summary.recommendation || "Review your topic scores below and practice again when you're ready.";

  const strengthsBlock = $("results-strengths-block");
  const improvementsBlock = $("results-improvements-block");
  const strengths = summary.strengths || [];
  const improvements = summary.areas_to_improve || [];

  if (strengths.length && strengthsBlock) {
    strengthsBlock.hidden = false;
    renderFeedbackList($("results-strengths-list"), strengths);
  } else if (strengthsBlock) {
    strengthsBlock.hidden = true;
  }

  if (improvements.length && improvementsBlock) {
    improvementsBlock.hidden = false;
    renderFeedbackList($("results-improvements-list"), improvements);
  } else if (improvementsBlock) {
    improvementsBlock.hidden = true;
  }

  const turns = result?.turns || [];
  const topicsWrap = $("results-topics-wrap");
  const topicsEl = $("results-topics");
  if (turns.length && topicsEl && topicsWrap) {
    topicsWrap.hidden = false;
    topicsEl.innerHTML = "";
    turns.forEach((turn, index) => {
      const ev = turn.evaluation;
      if (!ev) return;
      const card = document.createElement("div");
      card.className = "results-topic-card";
      card.dataset.tier = feedbackScoreTier(ev.score);
      card.innerHTML = `<strong>Topic ${(turn.prompt_index ?? index) + 1} · ${ev.score}/10</strong><p class="results-topic-text">${ev.feedback}</p>`;
      topicsEl.appendChild(card);
    });
  } else if (topicsWrap) {
    topicsWrap.hidden = true;
  }

  const adaptNotice = $("results-adaptation");
  if (result?.plan_adaptation?.adapted && adaptNotice) {
    adaptNotice.textContent = `✨ Days ${result.plan_adaptation.updated_days.join(", ")} updated: ${result.plan_adaptation.reason}`;
    adaptNotice.hidden = false;
  } else if (adaptNotice) {
    adaptNotice.hidden = true;
  }
}

function updateVoicePhaseLabel(text) {
  const el = $("recording-status");
  if (el) {
    el.textContent = text || "";
    el.hidden = true;
  }
}

function scheduleSilenceSubmit() {
  clearSilenceSubmitTimer();
  if (state.interviewBusy || state.coachSpeaking) return;

  silenceSubmitTimer = setTimeout(() => {
    silenceSubmitTimer = null;
    if (state.interviewBusy || state.coachSpeaking || !browserListeningActive) return;
    const text = getBrowserTranscriptText();
    if (text.length >= MIN_SPEECH_CHARS) {
      flushSpeechAndSubmit();
    }
  }, SILENCE_SUBMIT_MS);
}

function handleSpeechResult(event) {
  let interim = "";
  for (let i = event.resultIndex; i < event.results.length; i += 1) {
    const chunk = event.results[i][0].transcript;
    if (event.results[i].isFinal) {
      browserTranscript += chunk;
    } else {
      interim += chunk;
    }
  }
  browserInterim = interim;

  if (!browserListeningActive || state.coachSpeaking) return;

  const heard = getBrowserTranscriptText();
  if (heard) {
    updateLiveTranscript(browserInterim.trim(), browserTranscript.trim());
    updateVoicePhase("listening");
    updateVoicePhaseLabel("Listening…");
    setInterviewStatus("Listening…");
    scheduleSilenceSubmit();
  }
}

function stopContinuousListening() {
  clearSilenceSubmitTimer();
  browserListeningActive = false;
  if (speechRecognition) {
    try {
      speechRecognition.stop();
    } catch {
      /* ignore */
    }
    speechRecognition = null;
  }
}

function stopVoiceCapture() {
  stopContinuousListening();
  stopCoachSpeech();
  releaseMic();
  resetSpeechBuffers();
  clearAvatarReaction();
  const live = $("live-transcript");
  if (live) live.hidden = true;
}

function resetInterviewLobbyUI() {
  if ($("interview-action-area")?.dataset.phase === "complete") return;
  state.interviewJoined = false;
  state.joinInProgress = false;
  state.interviewPaused = false;
  state.interviewPhase = "lobby";
  updateVoicePhase("idle");
  updateVoicePhaseLabel("");
  setAvatarState("idle");
  setJoinButtonVisible(true);
  updateSessionActionButtons();
}

function stopInterviewVoice({ resetLobby = true } = {}) {
  stopVoiceCapture();
  if (resetLobby) {
    resetInterviewLobbyUI();
  }
}

function isSessionCompleted(status) {
  return status === "completed";
}

function setPracticeViewPhase(phase) {
  const area = $("interview-action-area");
  if (area) area.dataset.phase = phase === "complete" ? "complete" : "live";
  updateSessionActionButtons();
}

function clearInterviewCompleteUI() {
  setPracticeViewPhase("live");
  document.querySelector(".interview-main")?.classList.remove("is-complete");
}

function showInterviewCompleteUI(result) {
  document.querySelector(".interview-main")?.classList.add("is-complete");
  setPracticeViewPhase("complete");

  stopVoiceCapture();
  state.interviewJoined = false;
  state.joinInProgress = false;
  state.interviewPaused = false;
  state.interviewBusy = false;

  const joinBtn = $("btn-join-interview");
  if (joinBtn) {
    joinBtn.hidden = true;
    joinBtn.disabled = false;
    joinBtn.textContent = "🎤 Join interview";
  }
  const orb = $("voice-orb");
  if (orb) orb.hidden = true;
  $("topic-preview-card").hidden = true;
  setInterviewControlsEnabled(false);

  updateTopicProgress("Interview complete", result.total_rounds, result.total_rounds);
  updateVoicePhase("complete");
  updateVoicePhaseLabel("");
  setInterviewStatus("Interview complete");
  setAvatarState("idle");
}

function stopRecordingIfActive() {
  stopInterviewVoice();
}

function setJoinButtonVisible(visible) {
  const joinBtn = $("btn-join-interview");
  const orb = $("voice-orb");
  if (joinBtn) {
    joinBtn.hidden = !visible;
    joinBtn.disabled = false;
    joinBtn.textContent = "🎤 Join interview";
  }
  if (orb) orb.hidden = visible;
}

function updateSessionActionButtons() {
  const panel = $("interview-session-actions");
  const pauseBtn = $("btn-pause-interview");
  const resumeBtn = $("btn-resume-interview");
  const endBtn = $("btn-end-interview");
  if (!panel) return;

  const area = $("interview-action-area");
  if (area?.dataset.phase === "complete") {
    panel.hidden = true;
    return;
  }

  const active =
    state.interviewJoined && !state.joinInProgress && state.sessionStatus !== "completed";
  panel.hidden = !active;
  if (!active) return;

  if (state.interviewBusy) {
    if (pauseBtn) pauseBtn.hidden = true;
    if (resumeBtn) resumeBtn.hidden = true;
    if (endBtn) endBtn.disabled = true;
    return;
  }

  if (pauseBtn) pauseBtn.hidden = state.interviewPaused;
  if (resumeBtn) resumeBtn.hidden = !state.interviewPaused;
  if (endBtn) endBtn.disabled = false;
  if (pauseBtn) pauseBtn.disabled = false;
}

function pauseInterview() {
  if (!state.interviewJoined || state.interviewPaused || state.joinInProgress || state.interviewBusy) return;
  state.interviewPaused = true;
  stopContinuousListening();
  stopCoachSpeech();
  resetSpeechBuffers();
  $("live-transcript").hidden = true;
  updateVoicePhase("idle");
  updateVoicePhaseLabel("");
  setInterviewStatus("Interview paused");
  setAvatarState("idle");
  updateSessionActionButtons();
}

async function resumeInterview() {
  if (!state.interviewJoined || !state.interviewPaused || state.interviewBusy) return;
  state.interviewPaused = false;
  updateSessionActionButtons();
  if (state.speakMethod === "browser") {
    await startContinuousListening();
    setInterviewStatus("Listening — speak when ready");
  } else {
    setInterviewStatus("Type your response below");
  }
}

async function endInterviewSession() {
  if (!state.sessionId || state.interviewBusy || state.joinInProgress || !state.interviewJoined) return;
  const scored =
    state.interviewPhase === "interview"
      ? "Scores will be generated for any topics you completed."
      : "You ended before formal questions — a short summary will still be saved.";
  if (!window.confirm(`End this interview?\n\n${scored}`)) return;

  stopContinuousListening();
  stopCoachSpeech();
  state.interviewBusy = true;
  state.interviewPaused = false;
  updateSessionActionButtons();
  updateVoicePhase("thinking");
  updateVoicePhaseLabel("Wrapping up…");
  setInterviewStatus("Generating your final results…");

  try {
    const result = await api(`/session/${state.sessionId}/interview-end`, { method: "POST" });
    state.sessionStatus = "completed";
    await handleInterviewTurn(result);
  } catch (err) {
    showError($("practice-error"), err.message);
    setInterviewStatus("Could not end session — try again");
    updateVoicePhase(state.interviewPaused ? "idle" : "listening");
    updateVoicePhaseLabel(state.interviewPaused ? "" : "Listening…");
    updateSessionActionButtons();
  } finally {
    state.interviewBusy = false;
    updateSessionActionButtons();
  }
}

async function startContinuousListening() {
  if (!browserSttSupported || state.speakMethod !== "browser") return false;
  if (state.coachSpeaking || state.interviewBusy || state.interviewPaused) return false;
  if (browserListeningActive && speechRecognition) {
    updateVoicePhase("listening");
    updateVoicePhaseLabel("Listening…");
    return true;
  }

  await ensureMicPermission();
  resetSpeechBuffers();
  browserListeningActive = true;
  showError($("practice-error"), "");

  speechRecognition = new SpeechRecognitionCtor();
  speechRecognition.lang = "en-US";
  speechRecognition.continuous = true;
  speechRecognition.interimResults = true;
  speechRecognition.maxAlternatives = 1;
  speechRecognition.onresult = handleSpeechResult;

  speechRecognition.onerror = (event) => {
    if (event.error === "aborted" || event.error === "no-speech") return;
    if (event.error === "not-allowed") {
      showError($("practice-error"), "Microphone blocked. Allow mic access in browser settings.");
      stopContinuousListening();
      updateVoicePhase("idle");
      return;
    }
    if (browserListeningActive) {
      setTimeout(() => {
        if (browserListeningActive && !state.interviewBusy) startContinuousListening();
      }, 500);
    }
  };

  speechRecognition.onend = () => {
    if (!browserListeningActive) {
      speechRecognition = null;
      return;
    }
    try {
      speechRecognition.start();
    } catch {
      setTimeout(() => {
        if (browserListeningActive) startContinuousListening();
      }, 300);
    }
  };

  speechRecognition.start();
  updateVoicePhase("listening");
  updateVoicePhaseLabel("Listening…");
  updateLiveTranscript("", "");
  return true;
}

async function flushSpeechAndSubmit() {
  const text = getBrowserTranscriptText();
  if (!text || state.interviewBusy) return;

  clearSilenceSubmitTimer();
  stopContinuousListening();
  resetSpeechBuffers();
  $("live-transcript").hidden = true;
  await submitInterviewMessage(text);
}

function setInterviewStatus(text) {
  const el = $("interview-status");
  if (el) {
    el.textContent = text;
    el.dataset.phase = state.voicePhase || "idle";
  }
}

function appendChatBubble(role, text) {
  const chat = $("interview-chat");
  if (!chat || !text?.trim()) return;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  const label = role === "coach" ? "Interviewer" : "You";
  bubble.innerHTML = `<span class="chat-label">${label}</span>${text.trim()}`;
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

function renderInterviewChat(conversation) {
  const chat = $("interview-chat");
  if (!chat) return;
  chat.innerHTML = "";
  (conversation || []).forEach((entry) => appendChatBubble(entry.role, entry.text));
}

function setInterviewControlsEnabled(enabled) {
  const send = $("btn-interview-send");
  const input = $("interview-type-input");
  if (send) send.disabled = !enabled;
  if (input) input.disabled = !enabled;
}

async function submitInterviewMessage(text) {
  const message = text.trim();
  if (!message || !state.sessionId || state.interviewBusy) return;

  if (state.interviewPhase === "interview" && !state.lastTopicSubmitConfirmed) {
    const currentTopic = (state.interviewRoundIndex ?? 0) + 1;
    const total = state.feedbackTotalRounds || 4;
    if (currentTopic >= total) {
      const ok = window.confirm(
        `This is topic ${total} of ${total} — the final question for today.\n\nIf the interviewer accepts your answer, today's interview will end and you'll see your full scores.\n\nContinue?`
      );
      if (!ok) {
        if (state.speakMethod === "browser" && state.interviewJoined && !state.interviewPaused) {
          await startContinuousListening();
        }
        return;
      }
      state.lastTopicSubmitConfirmed = true;
    }
  }

  stopContinuousListening();
  state.interviewBusy = true;
  state.bargeInActive = false;
  setInterviewControlsEnabled(false);
  showError($("practice-error"), "");
  updateVoicePhase("thinking");
  updateVoicePhaseLabel("Scoring your answer…");
  setInterviewStatus("Scoring your answer…");

  try {
    const result = await api(`/session/${state.sessionId}/interview-turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        interviewer_name: state.interviewerName || "Alex",
      }),
    });
    await handleInterviewTurn(result);
  } catch (err) {
    showError($("practice-error"), err.message);
    setInterviewStatus("Speak your answer when ready");
    setInterviewControlsEnabled(true);
    if (state.speakMethod === "browser") {
      await startContinuousListening();
    }
  } finally {
    state.interviewBusy = false;
  }
}

async function handleInterviewTurn(result) {
  state.interviewPhase = result.interview_phase || state.interviewPhase;
  state.interviewRoundIndex = result.round_index ?? state.interviewRoundIndex;
  state.feedbackTotalRounds = result.total_rounds ?? state.feedbackTotalRounds;
  renderInterviewChat(result.conversation);

  if (state.interviewPhase === "greeting") {
    updateTopicProgress("Getting started");
    $("topic-preview-card").hidden = false;
    $("topic-preview-text").textContent = formatTopicPreviewShort(state.sessionStart);
  } else {
    $("topic-preview-card").hidden = true;
    const topicNum = Math.min(result.round_index + 1, result.total_rounds);
    updateTopicProgress(`Topic ${topicNum} of ${result.total_rounds}`, result.round_index, result.total_rounds);
  }

  if (result.feedback_skipped) {
    setInterviewStatus("Answer the question directly to get feedback");
  } else if (result.answer_feedback) {
    appendAnswerFeedback(result.answer_feedback, result.feedback_label || "Your reply");
  }

  if (isSessionCompleted(result.session_status)) {
    state.sessionStatus = "completed";
    if (state.sessionStart) state.sessionStart.status = "completed";
    state.lastSessionResult = result;
    if (result.plan_adaptation?.adapted) {
      refreshPlanScreen();
    }
    setInterviewStatus("Preparing your results…");
    speakCoachMessages(result.coach_messages, () => {
      showResultsPage(result);
      if (result.session_summary && state.ttsEnabled) {
        const s = result.session_summary;
        speakCoach(`Your session average was ${s.average_score} out of 10. ${s.recommendation}`);
      }
    });
    return;
  }

  setInterviewControlsEnabled(true);

  speakCoachMessages(result.coach_messages, async () => {
    state.bargeInActive = false;
    if (result.action === "begin_interview") {
      state.interviewPhase = "interview";
      state.interviewRoundIndex = 0;
      $("topic-preview-card").hidden = true;
      updateTopicProgress(`Topic 1 of ${result.total_rounds}`, 0, result.total_rounds);
    }
    if (state.speakMethod === "browser") {
      await resumeListeningAfterCoach();
      const label =
        state.interviewPhase === "greeting"
          ? "Listening — say hello or let them know you're ready"
          : "Listening — speak your answer";
      setInterviewStatus(label);
    } else {
      setInterviewStatus("Type your response below");
      updateVoicePhase("idle");
      updateVoicePhaseLabel("");
    }
  });
}

async function joinInterview() {
  if (!state.sessionId || state.interviewJoined || state.interviewBusy || state.joinInProgress) return;

  const joinBtn = $("btn-join-interview");
  state.joinInProgress = true;
  if (joinBtn) {
    joinBtn.disabled = true;
    joinBtn.textContent = "Connecting…";
  }
  showError($("practice-error"), "");
  updateInterviewerAvatar();
  updateSessionActionButtons();

  try {
    if (state.speakMethod === "browser") {
      await ensureMicPermission();
    }

    const result = await api(`/session/${state.sessionId}/interview-begin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interviewer_name: state.interviewerName || "Alex" }),
    });

    state.interviewJoined = true;
    state.interviewPaused = false;
    state.interviewPhase = result.interview_phase || "greeting";
    state.feedbackTotalRounds = result.total_rounds || state.feedbackTotalRounds;
    state.interviewRoundIndex = 0;
    setJoinButtonVisible(false);
    updateSessionActionButtons();

    renderInterviewChat(result.conversation);
    $("topic-preview-text").textContent = formatTopicPreviewShort(state.sessionStart);
    updateTopicProgress("Getting started");
    setInterviewControlsEnabled(true);
    updateSpeakHint();

    speakCoachMessages(result.coach_messages, async () => {
      state.bargeInActive = false;
      if (state.speakMethod === "browser") {
        await resumeListeningAfterCoach();
        setInterviewStatus("Listening — say hello when you're ready");
      } else {
        setInterviewStatus("Type your response below");
      }
    });
  } catch (err) {
    showError($("practice-error"), err.message);
    setJoinButtonVisible(true);
    updateSessionActionButtons();
  } finally {
    state.joinInProgress = false;
    updateSessionActionButtons();
  }
}

async function ensureMicPermission() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone not supported in this browser.");
  }
  if (micStream?.active) return;
  releaseMic();
  micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
}

function updateLiveTranscript(interim, final) {
  const el = $("live-transcript");
  el.hidden = false;
  el.textContent = final + (interim ? ` ${interim}` : "") || "Listening…";
}

function showReading(start) {
  setStep(3);
  showScreen("screen-reading");
  clearInterviewCompleteUI();
  stopInterviewVoice();

  $("reading-day-label").textContent = `Day ${start.day}`;
  $("reading-title").textContent = start.title;
  $("reading-time-pill").textContent = `${start.reading.duration_min} min read`;
  $("reading-content").textContent = start.reading.content;

  state.sessionStart = start;
  state.sessionId = start.session_id;
  state.nextPrompt = null;
  state.sessionStatus = start.status;
}

async function showPractice(start) {
  setStep(4);
  showScreen("screen-practice");
  clearInterviewCompleteUI();
  showError($("practice-error"), "");

  state.sessionStart = start;
  state.sessionId = start.session_id;
  state.sessionStatus = start.status;

  resetFeedbackPanel(start.total_prompts || 4);
  $("interview-type-input").value = "";
  $("live-transcript").hidden = true;
  updateTtsControls();
  updateInterviewerAvatar();
  syncAdaptPlanOption();

  $("practice-day-label").textContent = `Day ${start.day}`;
  $("practice-title").textContent = start.title;

  const conversation = start.interview_log?.length ? start.interview_log : [];
  renderInterviewChat(conversation);

  if (isSessionCompleted(start.status)) {
    showResultsPage({
      turns: start.turns,
      total_rounds: start.total_prompts || state.feedbackTotalRounds || 4,
      session_summary: start.session_summary,
      plan_adaptation: null,
      round_index: start.prompt_index ?? 0,
    });
    return;
  }

  stopInterviewVoice();
  state.lastTopicSubmitConfirmed = false;
  state.interviewRoundIndex = start.prompt_index ?? 0;
  $("topic-preview-card").hidden = false;
  $("topic-preview-text").textContent = formatTopicPreviewShort(start);
  state.interviewBusy = false;
  state.bargeInActive = false;
  state.interviewJoined = false;
  state.interviewPhase = start.interview_phase || "lobby";
  updateSpeakHint();
  updateTopicProgress("Ready to begin");

  if (conversation.length) {
    state.interviewJoined = true;
    setJoinButtonVisible(false);
  } else {
    state.interviewJoined = false;
    setJoinButtonVisible(true);
  }

  setInterviewControlsEnabled(!!conversation.length);
  updateVoicePhase("idle");
  updateVoicePhaseLabel("");
  setAvatarState("idle");
  setInterviewStatus(conversation.length ? "Continue when ready" : "Tap the mic to join");
  updateSessionActionButtons();
}

// Upload handlers
const fileInput = $("file-input");
const dropZone = $("drop-zone");
let selectedFile = null;

fileInput.addEventListener("change", () => {
  selectedFile = fileInput.files[0] || null;
  $("file-name").textContent = selectedFile ? selectedFile.name : "or drag and drop here";
  $("btn-upload").disabled = !selectedFile;
});

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file && file.name.toLowerCase().endsWith(".pdf")) {
    selectedFile = file;
    $("file-name").textContent = file.name;
    $("btn-upload").disabled = false;
  }
});

$("btn-upload").addEventListener("click", async () => {
  if (!selectedFile) return;
  showError($("upload-error"), "");
  $("btn-upload").disabled = true;
  try {
    await runPipeline(selectedFile);
  } catch (err) {
    showScreen("screen-upload");
    setStep(1);
    showError($("upload-error"), err.message);
    $("btn-upload").disabled = false;
  }
});

$("opt-adapt-plan")?.addEventListener("change", saveAdaptPlanPreference);

$("btn-start-day").addEventListener("click", async () => {
  const day = parseInt($("day-select").value, 10);
  saveAdaptPlanPreference();
  $("btn-start-day").disabled = true;
  try {
    const start = await api("/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        candidate_id: state.candidateId,
        day,
        adapt_plan: state.adaptPlanEnabled,
      }),
    });
    showReading(start);
  } catch (err) {
    alert(err.message);
  } finally {
    $("btn-start-day").disabled = false;
  }
});

$("btn-start-practice").addEventListener("click", () => {
  if (!state.sessionStart) return;
  showPractice(state.sessionStart);
});

$("btn-skip-reading").addEventListener("click", () => {
  if (!state.sessionStart) return;
  showPractice(state.sessionStart);
});

$("btn-view-focus").addEventListener("click", () => {
  showFocusAreasScreen();
});

$("btn-back-focus-plan").addEventListener("click", () => {
  setStep(2);
  showScreen("screen-plan");
});

$("btn-back-plan").addEventListener("click", () => {
  setStep(2);
  showScreen("screen-plan");
});

$("btn-back-reading").addEventListener("click", () => {
  if (!state.sessionStart) return;
  clearInterviewCompleteUI();
  stopInterviewVoice();
  showReading(state.sessionStart);
});

$("btn-tts-toggle").addEventListener("click", toggleCoachSpeech);
$("tts-voice-select").addEventListener("change", () => {
  state.ttsVoiceUri = $("tts-voice-select").value;
  localStorage.setItem("jobi_tts_voice", state.ttsVoiceUri);
  updateInterviewerAvatar();
  previewCoachVoice();
});

$("btn-join-interview")?.addEventListener("click", () => joinInterview());
$("btn-pause-interview")?.addEventListener("click", () => pauseInterview());
$("btn-resume-interview")?.addEventListener("click", () => resumeInterview());
$("btn-end-interview")?.addEventListener("click", () => endInterviewSession());

$("btn-interview-send")?.addEventListener("click", async () => {
  const text = $("interview-type-input").value.trim();
  if (!text) {
    showError($("practice-error"), "Type a response first.");
    return;
  }
  $("interview-type-input").value = "";
  await submitInterviewMessage(text);
});

$("interview-type-input")?.addEventListener("keydown", async (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("btn-interview-send")?.click();
  }
});

$("btn-results-plan")?.addEventListener("click", async () => {
  clearInterviewCompleteUI();
  setStep(2);
  showScreen("screen-plan");
  await refreshPlanScreen();
});

$("btn-results-back")?.addEventListener("click", () => {
  clearInterviewCompleteUI();
  setStep(2);
  showScreen("screen-plan");
});

$("btn-new-resume").addEventListener("click", () => {
  clearStorage();
  selectedFile = null;
  fileInput.value = "";
  $("file-name").textContent = "or drag and drop here";
  $("btn-upload").disabled = true;
  $("spinner").hidden = false;
  setStep(1);
  showScreen("screen-upload");
});

// Resume returning user with existing plan
async function tryRestore() {
  if (!state.candidateId) return;
  try {
    const plan = await api(`/plans/candidate/${state.candidateId}`);
    state.plan = { plan: plan.plan, candidate_id: plan.candidate_id };
    if (state.resumeId) {
      await showPlanReady();
      return;
    }
  } catch {
    clearStorage();
  }
}

async function initHealth() {
  try {
    const health = await api("/health");
    state.serverStt = !!health.stt;
    state.sttProvider = health.stt_provider || "none";
    state.forceBrowserStt = health.stt_provider === "browser" || !!health.browser_stt;
  } catch {
    state.serverStt = false;
    state.sttProvider = "none";
    state.forceBrowserStt = true;
  }
  updateSpeakHint();
}

updateTtsControls(false);
initHealth();
tryRestore();
