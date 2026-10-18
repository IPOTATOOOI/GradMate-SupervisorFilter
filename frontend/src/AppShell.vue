<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import {
  BadgeCheck,
  Bot,
  Bold,
  CalendarClock,
  CircleHelp,
  CircleUserRound,
  Download,
  Eraser,
  ExternalLink,
  Eye,
  FilePenLine,
  FileSpreadsheet,
  FolderUp,
  Globe2,
  Italic,
  Kanban,
  LayoutDashboard,
  ListFilter,
  ListOrdered,
  LoaderCircle,
  MailCheck,
  MailPlus,
  MailWarning,
  RefreshCw,
  Save,
  ScanSearch,
  Search,
  Send,
  Sparkles,
  TextCursorInput,
  Underline,
  Trash2,
  Upload,
  UploadCloud,
  UserRound,
  UsersRound,
} from "lucide-vue-next";

const API_BASE = import.meta.env.DEV ? "" : window.location.origin;

const views = [
  { id: "assistant", label: "智能申请助理", icon: Bot },
  { id: "dashboard", label: "首页概览", icon: LayoutDashboard },
  { id: "profile", label: "个人画像", icon: UserRound },
  { id: "resume", label: "AI 简历", icon: FilePenLine },
  { id: "practice", label: "题库练习", icon: CircleHelp },
  { id: "documents", label: "导师资料", icon: FolderUp },
  { id: "matching", label: "导师匹配", icon: ListFilter },
  { id: "contact", label: "联系进度", icon: Kanban },
  { id: "rag", label: "招生问答", icon: Search },
  { id: "questions", label: "可能问题", icon: CircleHelp },
  { id: "email", label: "邮件工作台", icon: MailPlus },
  { id: "ddl", label: "保研 DDL", icon: CalendarClock },
];

const navGroups = [
  {
    title: "智能协作",
    items: views.filter((item) => item.id === "assistant"),
  },
  {
    title: "准备材料",
    items: views.filter((item) => ["dashboard", "profile", "resume", "practice"].includes(item.id)),
  },
  {
    title: "导师申请",
    items: views.filter((item) => ["documents", "matching", "contact", "email"].includes(item.id)),
  },
  {
    title: "招生信息",
    items: views.filter((item) => ["rag", "questions", "ddl"].includes(item.id)),
  },
];

const activeView = ref("dashboard");
const backendOnline = ref(false);
const toast = ref("");
const toastVisible = ref(false);
let toastTimer;
const MAX_ATTACHMENT_FILE_SIZE = 8 * 1024 * 1024;
const MAX_ATTACHMENT_TOTAL_SIZE = 20 * 1024 * 1024;
const CONTACT_STATUSES = ["未联系", "已生成草稿", "已发送", "等待回复", "已回复", "需补材料", "已约面谈", "暂不招生"];
const CONTACT_AUTO_STATUSES = new Set(CONTACT_STATUSES.slice(0, 3));
const CONTACT_MANUAL_STATUSES = new Set(CONTACT_STATUSES.slice(3));

const dashboard = reactive({
  supervisor_count: 0,
  high_match_count: 0,
  missing_email_count: 0,
  draft_count: 0,
});
const applicationAssistant = reactive({
  message: "",
  loading: false,
  answer: "",
  recommendations: [],
  admission_sources: [],
  events: [],
});
const assistantHistory = reactive({
  open: false,
  loading: false,
  items: [],
});

const profile = reactive({
  name: "",
  university: "",
  major: "",
  interests: "",
  projects: "",
  rank: "",
  english: "",
  target_schools: "",
  target_colleges: "",
  application_type: "保研",
});

const ddl = reactive({
  source: "camp2026",
  query: "",
  loading: false,
  source_label: "2026 夏令营",
  sources: [],
  items: [],
  stats: { total: 0, upcoming: 0, urgent: 0, closed: 0, unknown: 0 },
  meta: {},
});
const ddlPager = reactive({
  page: 1,
  pageSize: 10,
});

const profileSummary = ref("请先填写并保存个人画像。");
const supervisors = ref([]);
const sourceInput = ref("");
const supervisorText = ref("");
const selectedSupervisorFile = ref(null);
const supervisorFileInput = ref(null);
const browserSearch = reactive({
  school: "",
  major: "",
  college: "",
  keywords: "",
  max_pages: 12,
  loading: false,
  showTrace: false,
  visited_pages: [],
  trace: [],
  imported: 0,
});
const documentPager = reactive({
  page: 1,
  pageSize: 10,
});
const matchingFilters = reactive({
  query: "",
  level: "",
  email: "",
});
const matchingSort = ref("newest");
const matchingPager = reactive({
  page: 1,
  pageSize: 6,
});
const questionLab = reactive({
  supervisor_id: "",
  focus: "",
  loading: false,
  result: null,
});
const questionHistory = reactive({
  open: false,
  loading: false,
  items: [],
});
const rag = reactive({
  file: null,
  kind: "招生简章",
  uploading: false,
  asking: false,
  question: "",
  school: "",
  college: "",
  use_browser: true,
  knowledge: { chunk_count: 0, files: [] },
  answer: "",
  sources: [],
  used_browser: false,
});
const contactBoard = reactive({
  activeStatus: "等待回复",
  draggingId: null,
  updatingId: null,
});
const resumeLab = reactive({
  target: "",
  highlights: "",
  sourceText: "",
  generated: "",
  sections: [],
  suggestions: [],
  review: null,
  generating: false,
  reviewing: false,
  progress: 0,
  uploadName: "",
  photo: "",
  photoName: "",
  style: "保研导师联系",
});
const resumeDraftState = reactive({
  restoring: false,
  saving: false,
});
let resumeDraftTimer = null;
let resumeDraftHydrating = false;
const ragHistory = reactive({
  open: false,
  loading: false,
  items: [],
});
const selectedSupervisorId = ref(null);
const homepagePreview = reactive({
  loading: false,
  image: "",
  error: "",
  url: "",
  mode: "empty",
  embedLoaded: false,
  requestId: 0,
});
let homepageEmbedTimer = null;
const emailTone = ref("正式版");
const editorMode = ref("edit");
const richEditor = ref(null);
const emailDraft = reactive({
  to: "",
  cc: "",
  subject: "",
  body: "",
  bodyHtml: "",
  attachmentNote: "",
});
const emailSendConfirm = reactive({
  visible: false,
  sending: false,
  sent: false,
  success: false,
  message: "",
  body: "",
});
const attachmentFiles = ref([]);
const attachmentInputVersion = ref(0);
const emailReview = ref(null);
const emailAiWork = reactive({
  generating: false,
  reviewing: false,
});
const emailAiStatus = reactive({
  checked: false,
  ready: false,
  configured: false,
  dependency_ready: false,
  provider: "",
  model_id: "",
  base_url: "",
  dependency_error: "",
});
const emailSmtpConfig = reactive({
  smtp_host: "",
  smtp_port: 465,
  smtp_use_ssl: true,
  smtp_use_tls: false,
  smtp_configured: false,
});

const viewTitle = computed(() => views.find((item) => item.id === activeView.value)?.label || "GradMate");

const latestSupervisors = computed(() => {
  return [...supervisors.value].sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
});

const documentTotalPages = computed(() => Math.max(1, Math.ceil(latestSupervisors.value.length / documentPager.pageSize)));

const pagedDocumentSupervisors = computed(() => {
  const start = (documentPager.page - 1) * documentPager.pageSize;
  return latestSupervisors.value.slice(start, start + documentPager.pageSize);
});

const filteredMatchingSupervisors = computed(() => {
  const query = matchingFilters.query.trim().toLowerCase();
  const items = supervisors.value.filter((item) => {
    const merged = [item.name, item.school, item.college, item.direction, item.email, item.source]
      .join(" ")
      .toLowerCase();
    const levelMatched = !matchingFilters.level || item.match_level === matchingFilters.level;
    const emailMatched =
      !matchingFilters.email ||
      (matchingFilters.email === "has" && item.email) ||
      (matchingFilters.email === "missing" && !item.email);
    return (!query || merged.includes(query)) && levelMatched && emailMatched;
  });
  return items.sort((left, right) => {
    if (matchingSort.value === "score") {
      return Number(right.match_score || 0) - Number(left.match_score || 0) || Number(right.id || 0) - Number(left.id || 0);
    }
    return Number(right.id || 0) - Number(left.id || 0);
  });
});
const practice = reactive({
  topicId: "",
  topics: [],
  questions: [],
  answers: {},
  loading: false,
  submitted: false,
  result: null,
});

const matchingTotalPages = computed(() => Math.max(1, Math.ceil(filteredMatchingSupervisors.value.length / matchingPager.pageSize)));

const pagedMatchingSupervisors = computed(() => {
  const start = (matchingPager.page - 1) * matchingPager.pageSize;
  return filteredMatchingSupervisors.value.slice(start, start + matchingPager.pageSize);
});
const ddlTotalPages = computed(() => Math.max(1, Math.ceil(ddl.items.length / ddlPager.pageSize)));

const pagedDdlItems = computed(() => {
  const start = (ddlPager.page - 1) * ddlPager.pageSize;
  return ddl.items.slice(start, start + ddlPager.pageSize);
});
const selectedSupervisor = computed(() =>
  supervisors.value.find((item) => Number(item.id) === Number(selectedSupervisorId.value)) || null
);
const practiceAllAnswered = computed(() =>
  practice.questions.length > 0 && practice.questions.every((item) => String(practice.answers[item.id] || "").trim())
);
const practiceResultMap = computed(() => {
  const results = practice.result?.results || [];
  return Object.fromEntries(results.map((item) => [item.id, item]));
});
const ragAnswerHtml = computed(() => ragMarkdownToHtml(rag.answer));
const emailPlainText = computed(() => htmlToText(emailDraft.bodyHtml || textToHtml(emailDraft.body)));
const hasEmailBody = computed(() => Boolean(emailPlainText.value || htmlToText(richEditor.value?.innerHTML || "")));
const emailStats = computed(() => {
  const text = emailPlainText.value || "";
  return {
    chars: text.length,
    lines: text ? text.split("\n").length : 0,
    paragraphs: text ? text.split(/\n\s*\n/).filter(Boolean).length : 0,
  };
});
const attachmentTotalSize = computed(() => attachmentFiles.value.reduce((total, item) => total + item.size, 0));
const attachmentSummary = computed(() => {
  if (!attachmentFiles.value.length) return emailDraft.attachmentNote;
  return attachmentFiles.value.map((item) => `${item.name}（${formatFileSize(item.size)}）`).join("、");
});
const emailPreviewBody = computed(() => {
  const attachmentLine = attachmentSummary.value ? `\n\n附件：${attachmentSummary.value}` : "";
  return `${emailPlainText.value || "邮件正文将在这里预览。"}${attachmentLine}`;
});
const emailPreviewHtml = computed(() => {
  const body = emailDraft.bodyHtml || "<p>邮件正文将在这里预览。</p>";
  const attachment = attachmentSummary.value ? `<p><strong>附件：</strong>${escapeHtml(attachmentSummary.value)}</p>` : "";
  return `${body}${attachment}`;
});
const selectedMentorMeta = computed(() => {
  if (!selectedSupervisor.value) {
    return {
      title: "尚未选择导师",
      subtitle: "从左侧队列选择导师后开始撰写",
      direction: "研究方向待确认",
      score: "-",
    };
  }
  return {
    title: selectedSupervisor.value.name || "待确认导师",
    subtitle:
      [selectedSupervisor.value.school, selectedSupervisor.value.college].filter(Boolean).join(" / ") ||
      "院校待确认",
    direction: selectedSupervisor.value.direction || "研究方向待补充",
    score: selectedSupervisor.value.match_score || 0,
  };
});
const emailReadiness = computed(() => {
  const checks = [
    { label: "收件人", done: Boolean(emailDraft.to) },
    { label: "主题", done: Boolean(emailDraft.subject) },
    { label: "正文", done: Boolean(emailPlainText.value) },
    { label: "附件", done: Boolean(attachmentSummary.value) },
  ];
  const doneCount = checks.filter((item) => item.done).length;
  return {
    checks,
    score: Math.round((doneCount / checks.length) * 100),
  };
});
const emailAiLabel = computed(() => {
  if (!backendOnline.value) return "后端未连接";
  if (!emailAiStatus.checked) return "检测中";
  if (emailAiStatus.ready) return "AI 已启用";
  if (!emailAiStatus.configured) return ".env 未配置模型";
  if (!emailAiStatus.dependency_ready) return "AI 依赖缺失";
  return "AI 暂不可用";
});
const emailAiDetail = computed(() => {
  if (!backendOnline.value) return "请先启动 127.0.0.1:8000 后端服务。";
  if (emailAiStatus.ready) {
    return `${emailAiStatus.provider || "模型"} · ${emailAiStatus.model_id || "未命名模型"}`;
  }
  if (emailAiStatus.dependency_error) return emailAiStatus.dependency_error;
  if (!emailAiStatus.configured) return "检查项目根目录 .env 中的模型配置。";
  return "生成时会显示模型返回的具体错误。";
});

const emailSmtpLabel = computed(() => {
  if (!backendOnline.value) return "后端未连接";
  return emailSmtpConfig.smtp_configured ? "发件账号已配置" : "发件账号未配置";
});
const emailSmtpDetail = computed(() => {
  if (!emailSmtpConfig.smtp_host) return "请在服务端 .env 中配置 SMTP 连接信息。";
  return `${emailSmtpConfig.smtp_host}:${emailSmtpConfig.smtp_port} · 凭据由服务端环境变量管理`;
});
const canGenerateResume = computed(() =>
  Boolean(
    resumeLab.target.trim() ||
      resumeLab.highlights.trim() ||
      resumeLab.sourceText.trim() ||
      profile.name ||
      profile.projects ||
      profile.interests,
  )
);
const resumePreviewHtml = computed(() => {
  const photo = resumeLab.photo
    ? `<img class="resume-id-photo" src="${resumeLab.photo}" alt="证件照预览" />`
    : "";
  return `${photo}${markdownToHtml(resumeLab.generated || "AI 生成的简历会显示在这里。")}`;
});
const contactStatusGroups = computed(() =>
  CONTACT_STATUSES.map((status) => ({
    status,
    auto: CONTACT_AUTO_STATUSES.has(status),
    count: supervisors.value.filter((item) => getContactStatus(item) === status).length,
    items: supervisors.value.filter((item) => getContactStatus(item) === status),
  })),
);
const activeContactGroup = computed(
  () => contactStatusGroups.value.find((group) => group.status === contactBoard.activeStatus) || contactStatusGroups.value[0],
);
const contactStats = computed(() => ({
  total: supervisors.value.length,
  manual: supervisors.value.filter((item) => CONTACT_MANUAL_STATUSES.has(getContactStatus(item))).length,
  waiting: supervisors.value.filter((item) => getContactStatus(item) === "等待回复").length,
  sent: supervisors.value.filter((item) => getContactStatus(item) === "已发送").length,
}));

const nextActions = computed(() => {
  const actions = [];
  if (!profile.major && !profile.interests) {
    actions.push("先完善个人画像，让匹配结果有依据。");
  }
  if (!supervisors.value.length) {
    actions.push("导入导师资料后，系统会生成导师库。");
  }
  if (supervisors.value.length && dashboard.missing_email_count > 0) {
    actions.push(`有 ${dashboard.missing_email_count} 位导师缺少邮箱，建议补充来源。`);
  }
  if (supervisors.value.length) {
    actions.push("进入导师匹配页，计算匹配评分并按优先级排序。");
  }
  actions.push("查看保研 DDL，优先处理 7 天内截止的招生通知。");
  return actions;
});

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }
  return response.json();
}

function exportGet(path, format = "docx") {
  const separator = path.includes("?") ? "&" : "?";
  window.open(`${API_BASE}${path}${separator}format=${format}`, "_blank", "noopener");
}

async function exportPost(path, payload, format = "docx") {
  try {
    const response = await fetch(`${API_BASE}${path}?format=${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!response.ok) {
      throw new Error(`export failed: ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
    const filename = filenameMatch?.[1] || `GradMate_export.${format}`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast(format === "xlsx" ? "Excel 已生成" : "Word 已生成");
  } catch (error) {
    showToast("导出失败，请确认后端依赖已安装。");
  }
}

function exportDdl(format = "docx") {
  const params = new URLSearchParams({
    source: ddl.source,
    query: ddl.query.trim(),
    limit: "80",
  });
  exportGet(`/api/export/ddl?${params.toString()}`, format);
}

function exportRagAnswer(format = "docx") {
  exportPost("/api/export/rag-answer", {
    question: rag.question,
    answer: rag.answer,
    sources: rag.sources,
  }, format);
}

function exportQuestionResult(format = "docx") {
  if (!questionLab.result) return;
  exportPost("/api/export/questions", questionLab.result, format);
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

function clampPage(pager, totalPages) {
  if (pager.page > totalPages) {
    pager.page = totalPages;
  }
  if (pager.page < 1) {
    pager.page = 1;
  }
}

function resetDocumentPage() {
  documentPager.page = 1;
}

function resetMatchingPage() {
  matchingPager.page = 1;
}

function resetDdlPage() {
  ddlPager.page = 1;
}

function showToast(message) {
  clearTimeout(toastTimer);
  toast.value = message;
  toastVisible.value = true;
  toastTimer = setTimeout(() => {
    toastVisible.value = false;
  }, 2600);
}

function formatFileSize(size = 0) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size >= 1024) return `${Math.round(size / 1024)} KB`;
  return `${size} B`;
}

function getContactStatus(item = {}) {
  const status = String(item.contact_status || "").trim();
  if (CONTACT_MANUAL_STATUSES.has(status)) return status;
  if (status === "已发送" || item.email_sent_at) return "已发送";
  if (status === "已生成草稿" || item.email_body || item.email_subject) return "已生成草稿";
  return "未联系";
}

function getContactDate(item = {}) {
  return item.contact_last_at || item.email_sent_at || item.email_generated_at || "";
}

function daysSince(value) {
  if (!value) return null;
  const then = new Date(`${value}T00:00:00`);
  if (Number.isNaN(then.getTime())) return null;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.max(0, Math.floor((today.getTime() - then.getTime()) / 86400000));
}

function contactSuggestion(item = {}) {
  const status = getContactStatus(item);
  const days = daysSince(getContactDate(item));
  if (status === "未联系") return item.email ? "可先生成联系草稿。" : "建议先补充导师邮箱。";
  if (status === "已生成草稿") return "草稿已准备好，可进入邮件工作台最终确认。";
  if (status === "已发送") return "已发送邮件，可按实际情况拖到等待回复。";
  if (status === "等待回复") {
    if (days !== null && days >= 5) return `已等待 ${days} 天，可准备礼貌跟进邮件。`;
    return days !== null ? `已等待 ${days} 天，继续观察回复。` : "等待导师回复中。";
  }
  if (status === "已回复") return "记录回复内容，准备下一步沟通。";
  if (status === "需补材料") return "优先补齐导师要求的材料。";
  if (status === "已约面谈") return "整理项目经历和可能问题。";
  return "暂不作为近期跟进对象。";
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function markdownToHtml(value = "") {
  const lines = String(value || "").split(/\r?\n/);
  const html = [];
  let listType = "";
  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = "";
    }
  };
  const openList = (type) => {
    if (listType === type) return;
    closeList();
    html.push(`<${type}>`);
    listType = type;
  };
  const formatInline = (text = "") => {
    let content = escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
    content = content.replace(
      /^([\u4e00-\u9fa5A-Za-z0-9\s]{2,14}[：:])/,
      '<strong class="resume-key-label">$1</strong>',
    );
    return content.replace(
      /(IoU|Dice|SAM|LoRA|ViT\+CNN|CPI|CPU|[0-9]+(?:\.[0-9]+)?%|国家级|省级|一等奖|二等奖|三等奖|优秀营员|核心成员|负责人|第一作者|共同一作)/g,
      '<span class="resume-highlight">$1</span>',
    );
  };
  const projectHeading = (text = "") => {
    const parts = text.split("|").map((part) => part.trim()).filter(Boolean);
    if (parts.length <= 1) return `<h4>${formatInline(text)}</h4>`;
    return `<h4 class="resume-project-title"><span>${formatInline(parts[0])}</span><small>${parts.slice(1).map(formatInline).join(" / ")}</small></h4>`;
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      return;
    }
    if (/^####\s+/.test(trimmed)) {
      closeList();
      html.push(projectHeading(trimmed.replace(/^####\s+/, "")));
      return;
    }
    if (/^###\s+/.test(trimmed)) {
      closeList();
      html.push(projectHeading(trimmed.replace(/^###\s+/, "")));
      return;
    }
    if (trimmed.startsWith("## ")) {
      closeList();
      html.push(`<h3>${formatInline(trimmed.slice(3))}</h3>`);
      return;
    }
    if (trimmed.startsWith("# ")) {
      closeList();
      html.push(`<h2>${formatInline(trimmed.slice(2))}</h2>`);
      return;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      openList("ul");
      html.push(`<li>${formatInline(trimmed.replace(/^[-*]\s+/, ""))}</li>`);
      return;
    }
    if (/^\d+[.、)]\s+/.test(trimmed)) {
      openList("ol");
      html.push(`<li>${formatInline(trimmed.replace(/^\d+[.、)]\s+/, ""))}</li>`);
      return;
    }
    closeList();
    html.push(`<p>${formatInline(trimmed)}</p>`);
  });
  closeList();
  return html.join("");
}

function ragMarkdownToHtml(value = "") {
  const html = [];
  let listOpen = false;
  const closeList = () => {
    if (listOpen) html.push("</ul>");
    listOpen = false;
  };
  const inline = (text = "") => {
    let content = escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
    return content.replace(/(https?:\/\/[^\s<]+)/g, (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
  };
  String(value || "").split(/\r?\n/).forEach((line) => {
    const text = line.trim();
    if (!text) {
      closeList();
    } else if (/^###\s+/.test(text)) {
      closeList();
      html.push(`<h3>${inline(text.replace(/^###\s+/, ""))}</h3>`);
    } else if (/^##\s+/.test(text)) {
      closeList();
      html.push(`<h2>${inline(text.replace(/^##\s+/, ""))}</h2>`);
    } else if (/^[-*]\s+/.test(text)) {
      if (!listOpen) html.push("<ul>");
      listOpen = true;
      html.push(`<li>${inline(text.replace(/^[-*]\s+/, ""))}</li>`);
    } else {
      closeList();
      html.push(`<p>${inline(text)}</p>`);
    }
  });
  closeList();
  return html.join("");
}

function textToHtml(value = "") {
  if (!value.trim()) return "";
  return value
    .split(/\n{2,}/)
    .map((paragraph) => `<p>${escapeHtml(paragraph).replaceAll("\n", "<br>")}</p>`)
    .join("");
}

function htmlToText(value = "") {
  const container = document.createElement("div");
  container.innerHTML = value;
  container.querySelectorAll("br").forEach((node) => node.replaceWith("\n"));
  container.querySelectorAll("p,div,li").forEach((node) => node.append("\n"));
  return container.textContent.replace(/\n{3,}/g, "\n\n").trim();
}

async function renderRichEditor() {
  await nextTick();
  if (richEditor.value && richEditor.value.innerHTML !== emailDraft.bodyHtml) {
    richEditor.value.innerHTML = emailDraft.bodyHtml;
  }
}

function setEmailBody(value = "") {
  emailDraft.body = value;
  emailDraft.bodyHtml = textToHtml(value);
  renderRichEditor();
}

function syncRichEditor() {
  emailDraft.bodyHtml = richEditor.value?.innerHTML || "";
  emailDraft.body = emailPlainText.value;
}

function getCurrentEmailBody() {
  if (richEditor.value) {
    emailDraft.bodyHtml = richEditor.value.innerHTML || "";
  }
  emailDraft.body = htmlToText(emailDraft.bodyHtml || textToHtml(emailDraft.body));
  return emailDraft.body;
}

function fileToAttachmentPayload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      resolve({
        name: file.name,
        size: file.size,
        type: file.type || "application/octet-stream",
        data: dataUrl.includes(",") ? dataUrl.split(",").pop() : dataUrl,
      });
    };
    reader.onerror = () => reject(reader.error || new Error(`读取附件失败：${file.name}`));
    reader.readAsDataURL(file);
  });
}

async function buildAttachmentPayloads() {
  return Promise.all(attachmentFiles.value.map((item) => fileToAttachmentPayload(item.file || item)));
}

function applyRichCommand(command) {
  if (!richEditor.value) return;
  richEditor.value.focus();
  document.execCommand(command, false, null);
  syncRichEditor();
}

function clearAttachments() {
  attachmentFiles.value = [];
  emailDraft.attachmentNote = "";
  attachmentInputVersion.value += 1;
}

async function clearEmailAttachments() {
  clearAttachments();
  if (!selectedSupervisor.value) return;
  selectedSupervisor.value.email_attachment_note = "";
  selectedSupervisor.value.email_attachment_files = [];
  selectedSupervisor.value.email_attachment_total_size = 0;
  try {
    await api("/api/email/attachments/clear", {
      method: "POST",
      body: JSON.stringify({ supervisor_id: selectedSupervisor.value.id }),
    });
    showToast("附件已清空");
  } catch (error) {
    showToast("附件已从当前编辑区清空，保存到后端失败");
  }
}

function removeAttachment(index) {
  attachmentFiles.value.splice(index, 1);
  if (!attachmentFiles.value.length) {
    emailDraft.attachmentNote = "";
    attachmentInputVersion.value += 1;
    return;
  }
  emailDraft.attachmentNote = attachmentSummary.value;
}

function handleAttachmentUpload(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) {
    clearAttachments();
    return;
  }
  const oversized = files.find((file) => file.size > MAX_ATTACHMENT_FILE_SIZE);
  if (oversized) {
    event.target.value = "";
    attachmentInputVersion.value += 1;
    showToast(`${oversized.name} 超过 ${formatFileSize(MAX_ATTACHMENT_FILE_SIZE)}，请压缩后再上传`);
    return;
  }
  const totalSize = files.reduce((total, file) => total + file.size, 0);
  if (totalSize > MAX_ATTACHMENT_TOTAL_SIZE) {
    event.target.value = "";
    attachmentInputVersion.value += 1;
    showToast(`附件总大小不能超过 ${formatFileSize(MAX_ATTACHMENT_TOTAL_SIZE)}`);
    return;
  }
  attachmentFiles.value = files.map((file) => ({ name: file.name, size: file.size, type: file.type, file }));
  emailDraft.attachmentNote = attachmentSummary.value;
}

function applyProfile(data = {}) {
  Object.assign(profile, {
    name: "",
    university: "",
    major: "",
    interests: "",
    projects: "",
    rank: "",
    english: "",
    target_schools: "",
    target_colleges: "",
    application_type: "保研",
    ...data,
  });
}

function applyEmailConfig(data = {}) {
  Object.assign(emailSmtpConfig, {
    smtp_host: data.smtp_host || "",
    smtp_port: Number(data.smtp_port || 465),
    smtp_use_ssl: data.smtp_use_ssl !== false,
    smtp_use_tls: Boolean(data.smtp_use_tls),
    smtp_configured: Boolean(data.smtp_configured),
  });
}

function statusText(status) {
  return {
    urgent: "即将截止",
    upcoming: "报名中",
    closed: "已截止",
    unknown: "待确认",
  }[status] || "待确认";
}

function daysText(item) {
  if (item.days_left === null || item.days_left === undefined) return "日期待确认";
  if (item.days_left < 0) return `已过 ${Math.abs(item.days_left)} 天`;
  if (item.days_left === 0) return "今天截止";
  return `还剩 ${item.days_left} 天`;
}

async function fetchDDL(refresh = false) {
  ddl.loading = true;
  try {
    const params = new URLSearchParams({
      source: ddl.source,
      query: ddl.query.trim(),
      limit: "60",
      refresh: String(refresh),
    });
    const result = await api(`/api/baoyan-ddl?${params.toString()}`);
    Object.assign(ddl, {
      source: result.source || ddl.source,
      source_label: result.source_label || ddl.source_label,
      sources: result.sources || ddl.sources,
      items: result.items || [],
      stats: result.stats || ddl.stats,
      meta: result.meta || {},
    });
    resetDdlPage();
  } catch (error) {
    showToast("保研 DDL 数据加载失败，请确认后端已启动且网络可访问 GitHub。");
  } finally {
    ddl.loading = false;
  }
}

async function runApplicationAssistant() {
  if (!applicationAssistant.message.trim() || applicationAssistant.loading) return;
  applicationAssistant.loading = true;
  applicationAssistant.answer = "";
  applicationAssistant.recommendations = [];
  applicationAssistant.admission_sources = [];
  applicationAssistant.events = [{
    event: "on_chain_start",
    name: "gradmate_application_agent",
    message: "正在连接 GradMate 智能申请助理……",
    time: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
  }];
  try {
    const response = await fetch(`${API_BASE}/api/assistant/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: applicationAssistant.message.trim() }),
    });
    if (!response.ok || !response.body) throw new Error(`请求失败：${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const type = frame.match(/^event: (.+)$/m)?.[1] || "message";
        const raw = frame.match(/^data: (.+)$/m)?.[1];
        if (!raw) continue;
        const data = JSON.parse(raw);
        if (type === "event") applicationAssistant.events.push(data);
        if (type === "result") result = data;
        if (type === "error") throw new Error(data.detail || "任务执行失败");
      }
      if (done) break;
    }
    if (!result) throw new Error("未收到任务结果");
    applicationAssistant.answer = result.answer || "任务已完成。";
    applicationAssistant.recommendations = result.recommendations || [];
    applicationAssistant.admission_sources = result.admission_sources || [];
    if (assistantHistory.open) await loadAssistantHistory();
    await refreshAll();
  } catch (error) {
    applicationAssistant.events.push({
      event: "on_chain_end",
      name: "gradmate_application_agent",
      message: `任务执行失败：${error.message || "请确认后端已启动"}`,
      time: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
    });
    showToast("智能申请助理执行失败，请确认后端已启动");
  } finally {
    applicationAssistant.loading = false;
  }
}

async function loadAssistantHistory() {
  assistantHistory.loading = true;
  try {
    const result = await api("/api/assistant/history?limit=30");
    assistantHistory.items = result.items || [];
  } catch (error) {
    showToast("智能申请助理历史记录加载失败");
  } finally {
    assistantHistory.loading = false;
  }
}

async function toggleAssistantHistory() {
  assistantHistory.open = !assistantHistory.open;
  if (assistantHistory.open) await loadAssistantHistory();
}

function restoreAssistantHistory(item) {
  applicationAssistant.message = item.message || "";
  applicationAssistant.answer = item.answer || "";
  applicationAssistant.recommendations = item.recommendations || [];
  applicationAssistant.admission_sources = item.admission_sources || [];
  applicationAssistant.events = item.events || [];
  showToast("已恢复这次智能申请任务的结果与执行过程");
}

async function refreshAll() {
  try {
    await api("/api/health");
    backendOnline.value = true;
    const [dashboardResult, profileResult, supervisorsResult, emailConfigResult] = await Promise.all([
      api("/api/dashboard"),
      api("/api/profile"),
      api("/api/supervisors"),
      api("/api/email/config"),
    ]);
    Object.assign(dashboard, dashboardResult);
    applyProfile(profileResult.profile || {});
    profileSummary.value = profileResult.summary || "请先填写并保存个人画像。";
    supervisors.value = supervisorsResult.supervisors || [];
    clampPage(documentPager, documentTotalPages.value);
    clampPage(matchingPager, matchingTotalPages.value);
    applyEmailConfig(emailConfigResult);
    Object.assign(emailAiStatus, {
      checked: true,
      ready: Boolean(emailConfigResult.ready),
      configured: Boolean(emailConfigResult.configured),
      dependency_ready: Boolean(emailConfigResult.dependency_ready),
      provider: emailConfigResult.provider || "",
      model_id: emailConfigResult.model_id || "",
      base_url: emailConfigResult.base_url || "",
      dependency_error: emailConfigResult.dependency_error || "",
    });
  } catch (error) {
    backendOnline.value = false;
    Object.assign(emailAiStatus, {
      checked: false,
      ready: false,
      configured: false,
      dependency_ready: false,
      provider: "",
      model_id: "",
      base_url: "",
      dependency_error: "",
    });
    showToast("后端未连接，请先运行 conda run -n potatopy3.13 python backend\\app.py");
  }
}

async function saveProfile() {
  try {
    const result = await api("/api/profile", {
      method: "POST",
      body: JSON.stringify(profile),
    });
    applyProfile(result.profile || {});
    profileSummary.value = result.summary || "";
    await refreshAll();
    showToast("个人画像已保存");
  } catch (error) {
    showToast("保存失败，请确认后端已启动");
  }
}

async function loadFile(event) {
  const file = event.target.files?.[0] || null;
  selectedSupervisorFile.value = file;
  if (!file) return;
  if (!sourceInput.value) {
    sourceInput.value = file.name;
  }
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  const isXlsx = file.name.toLowerCase().endsWith(".xlsx");
  if (isPdf || isXlsx) {
    supervisorText.value = "";
    showToast(`已选择 ${isXlsx ? "XLSX" : "PDF"}，点击上传后由后端解析并抽取`);
    return;
  }
  supervisorText.value = await file.text();
  showToast("已读取文件内容，可以上传抽取");
}

async function uploadSupervisors() {
  const currentFile = selectedSupervisorFile.value || supervisorFileInput.value?.files?.[0] || null;
  if (currentFile) {
    try {
      browserSearch.loading = true;
      showToast("文件上传中，正在抽取导师资料...");
      const formData = new FormData();
      formData.append("file", currentFile);
      formData.append("source", sourceInput.value || currentFile.name || "用户上传资料");
      const response = await fetch(`${API_BASE}/api/supervisors/upload-file`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `upload failed: ${response.status}`);
      }
      const result = await response.json();
      supervisors.value = result.supervisors || [];
      selectedSupervisorFile.value = null;
      if (supervisorFileInput.value) {
        supervisorFileInput.value.value = "";
      }
      resetDocumentPage();
      resetMatchingPage();
      matchingSort.value = "newest";
      await refreshAll();
      showToast(`已从文件抽取 ${result.imported || 0} 条导师资料（${result.method || "unknown"}，文本 ${result.text_length || 0} 字）`);
    } catch (error) {
      showToast(`文件上传失败：${error.message || "请确认后端依赖和模型配置可用"}`);
    } finally {
      browserSearch.loading = false;
    }
    return;
  }

  if (!supervisorText.value.trim()) {
    showToast("请先粘贴或选择导师资料文件");
    return;
  }
  try {
    showToast("正在抽取导师资料...");
    const result = await api("/api/supervisors/upload", {
      method: "POST",
      body: JSON.stringify({
        text: supervisorText.value,
        source: sourceInput.value || "用户上传资料",
      }),
    });
    supervisors.value = result.supervisors || [];
    resetDocumentPage();
    resetMatchingPage();
    matchingSort.value = "newest";
    await refreshAll();
    showToast(`已抽取 ${result.imported || 0} 条导师资料（${result.method || "unknown"}）`);
  } catch (error) {
    showToast("上传失败，请确认后端已启动");
  }
}

async function deleteSupervisor(item) {
  const name = item?.name || "该导师";
  if (!window.confirm(`确认删除 ${name} 的导师资料吗？`)) {
    return;
  }
  try {
    const result = await api(`/api/supervisors/${item.id}`, {
      method: "DELETE",
    });
    supervisors.value = result.supervisors || [];
    resetDocumentPage();
    resetMatchingPage();
    await refreshAll();
    showToast("导师资料已删除");
  } catch (error) {
    showToast("删除失败，请刷新后重试");
  }
}

async function browseSupervisorSites() {
  if (!browserSearch.school.trim() || !(browserSearch.major.trim() || browserSearch.college.trim())) {
    showToast("请填写学校，并至少填写专业或学院关键词");
    return;
  }
  browserSearch.loading = true;
  try {
    const result = await api("/api/supervisors/agent-browse", {
      method: "POST",
      body: JSON.stringify({
        school: browserSearch.school,
        major: browserSearch.major,
        college: browserSearch.college,
        keywords: browserSearch.keywords,
        max_pages: browserSearch.max_pages,
        save: true,
      }),
    });
    browserSearch.visited_pages = result.visited_pages || [];
    browserSearch.trace = result.trace || [];
    browserSearch.imported = result.imported || 0;
    supervisors.value = result.supervisors || [];
    resetDocumentPage();
    resetMatchingPage();
    matchingSort.value = "newest";
    await refreshAll();
    showToast(`官网检索完成，已导入 ${browserSearch.imported} 条导师资料`);
  } catch (error) {
    showToast("官网检索失败，请确认 chromedriver 路径、Chrome 浏览器和网络连接可用");
  } finally {
    browserSearch.loading = false;
  }
}

async function matchSupervisors() {
  try {
    const result = await api("/api/supervisors/match", {
      method: "POST",
      body: "{}",
    });
    supervisors.value = result.supervisors || [];
    profileSummary.value = result.profile_summary || profileSummary.value;
    resetMatchingPage();
    matchingSort.value = "score";
    await refreshAll();
    showToast("导师匹配评分已更新");
  } catch (error) {
    showToast("匹配失败，请先保存画像并启动后端");
  }
}

async function generateQuestions() {
  if (!questionLab.supervisor_id) {
    showToast("请先选择导师");
    return;
  }
  questionLab.loading = true;
  try {
    showToast("正在生成可能问题...");
    const result = await api("/api/questions/generate", {
      method: "POST",
      body: JSON.stringify({
        supervisor_id: Number(questionLab.supervisor_id),
        focus: questionLab.focus,
      }),
    });
    questionLab.result = result.questions || null;
    if (questionHistory.open) loadQuestionHistory();
    showToast("可能问题已生成");
  } catch (error) {
    showToast(`生成失败：${error.message || "请确认模型配置可用"}`);
  } finally {
    questionLab.loading = false;
  }
}

async function loadPracticeQuestions() {
  practice.loading = true;
  practice.submitted = false;
  practice.result = null;
  practice.answers = {};
  try {
    const topicsResult = await api("/api/practice/topics");
    practice.topics = topicsResult.topics || [];
    if (!practice.topicId || !practice.topics.some((item) => item.id === practice.topicId)) {
      practice.topicId = practice.topics[0]?.id || "";
    }
    if (!practice.topicId) {
      practice.questions = [];
      return;
    }
    const questionsResult = await api(`/api/practice/questions?topic_id=${encodeURIComponent(practice.topicId)}`);
    practice.questions = questionsResult.questions || [];
  } catch (error) {
    practice.questions = [];
    showToast(`题库加载失败：${error.message || "请确认后端已启动"}`);
  } finally {
    practice.loading = false;
  }
}

async function submitPracticeAnswers() {
  if (practice.submitted) {
    showToast("本组题目已提交，可点击“换一组题”继续练习");
    return;
  }
  try {
    practice.result = await api("/api/practice/submit", {
      method: "POST",
      body: JSON.stringify({ answers: practice.answers, question_ids: practice.questions.map((item) => item.id) }),
    });
    practice.submitted = true;
    showToast(`客观题得分：${practice.result.score} 分`);
  } catch (error) {
    showToast(`提交失败：${error.message || "请稍后重试"}`);
  }
}

async function loadQuestionHistory() {
  questionHistory.loading = true;
  try {
    const result = await api("/api/questions/history?limit=30");
    questionHistory.items = result.items || [];
  } catch (error) {
    notify(error.message || "历史记录加载失败");
  } finally {
    questionHistory.loading = false;
  }
}

async function toggleQuestionHistory() {
  questionHistory.open = !questionHistory.open;
  if (questionHistory.open) await loadQuestionHistory();
}

function restoreQuestionHistory(item) {
  questionLab.supervisor_id = Number(item.supervisor_id) || "";
  questionLab.focus = item.focus || "";
  questionLab.result = item.questions || null;
}

async function fetchKnowledge() {
  try {
    rag.knowledge = await api("/api/knowledge");
  } catch (error) {
    rag.knowledge = { chunk_count: 0, files: [] };
  }
}

function loadKnowledgeFile(event) {
  rag.file = event.target.files?.[0] || null;
}

async function uploadKnowledge() {
  if (!rag.file) {
    showToast("请先选择招生简章、学院通知或导师介绍文件");
    return;
  }
  rag.uploading = true;
  try {
    const formData = new FormData();
    formData.append("file", rag.file);
    formData.append("kind", rag.kind);
    const response = await fetch(`${API_BASE}/api/knowledge/upload`, { method: "POST", body: formData });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `upload failed: ${response.status}`);
    }
    const result = await response.json();
    await fetchKnowledge();
    showToast(`已入库 ${result.chunks || 0} 个片段`);
  } catch (error) {
    showToast(`知识库上传失败：${error.message || "请确认文件可解析"}`);
  } finally {
    rag.uploading = false;
  }
}

async function askRag() {
  if (!rag.question.trim()) {
    showToast("请先输入问题");
    return;
  }
  rag.asking = true;
  try {
    const result = await api("/api/rag/ask", {
      method: "POST",
      body: JSON.stringify({
        question: rag.question,
        school: rag.school,
        college: rag.college,
        use_browser: rag.use_browser,
      }),
    });
    rag.answer = result.answer || "";
    rag.sources = result.sources || [];
    rag.used_browser = !!result.used_browser;
    if (ragHistory.open) loadRagHistory();
    showToast(result.used_browser ? "已结合网页检索生成回答" : "已基于知识库生成回答");
  } catch (error) {
    showToast(`问答失败：${error.message || "请确认后端和模型配置可用"}`);
  } finally {
    rag.asking = false;
  }
}

async function loadResumeSourceFile(event) {
  const file = event.target.files?.[0] || null;
  if (!file) return;
  resumeLab.uploadName = file.name;
  try {
    if (file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf") {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`${API_BASE}/api/resume/upload-file`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        const text = await response.text();
        let message = text;
        try {
          message = JSON.parse(text).detail || text;
        } catch {
          message = text;
        }
        throw new Error(message || `upload failed: ${response.status}`);
      }
      const result = await response.json();
      resumeLab.sourceText = result.text || "";
    } else {
      resumeLab.sourceText = await file.text();
    }
    showToast("已读取简历文本，可继续生成 AI 简历");
  } catch (error) {
    showToast(`文件读取失败：${error.message || "请粘贴简历文本，或上传 txt/md/csv/pdf 文件"}`);
  } finally {
    event.target.value = "";
  }
}

function resumeDraftPayload() {
  return {
    target: resumeLab.target,
    highlights: resumeLab.highlights,
    source_text: resumeLab.sourceText,
    generated: resumeLab.generated,
    sections: resumeLab.sections,
    suggestions: resumeLab.suggestions,
    review: resumeLab.review,
    upload_name: resumeLab.uploadName,
    photo: resumeLab.photo,
    photo_name: resumeLab.photoName,
    style: resumeLab.style,
  };
}

function hasResumeDraftContent(draft = resumeLab) {
  return Boolean(
    draft.target || draft.highlights || draft.sourceText || draft.source_text || draft.generated ||
    draft.uploadName || draft.upload_name || draft.photo || draft.sections?.length || draft.suggestions?.length || draft.review,
  );
}

async function saveResumeDraft({ silent = true } = {}) {
  if (resumeDraftHydrating || !hasResumeDraftContent()) return;
  resumeDraftState.saving = true;
  try {
    await api("/api/resume/draft", {
      method: "POST",
      body: JSON.stringify(resumeDraftPayload()),
    });
    if (!silent) showToast("AI 简历内容已保存");
  } catch (error) {
    if (!silent) showToast("AI 简历保存失败，请确认后端已启动");
  } finally {
    resumeDraftState.saving = false;
  }
}

function scheduleResumeDraftSave() {
  if (resumeDraftHydrating || resumeLab.generating || resumeLab.reviewing) return;
  window.clearTimeout(resumeDraftTimer);
  resumeDraftTimer = window.setTimeout(() => {
    saveResumeDraft();
  }, 700);
}

async function loadResumeDraft() {
  resumeDraftState.restoring = true;
  try {
    const result = await api("/api/resume/draft");
    const draft = result.draft || {};
    if (!hasResumeDraftContent(draft)) return;
    resumeDraftHydrating = true;
    Object.assign(resumeLab, {
      target: draft.target || "",
      highlights: draft.highlights || "",
      sourceText: draft.source_text || "",
      generated: draft.generated || "",
      sections: Array.isArray(draft.sections) ? draft.sections : [],
      suggestions: Array.isArray(draft.suggestions) ? draft.suggestions : [],
      review: draft.review || null,
      uploadName: draft.upload_name || "",
      photo: draft.photo || "",
      photoName: draft.photo_name || "",
      style: draft.style || "保研导师联系",
      progress: draft.generated ? 100 : 0,
    });
    showToast("已恢复上一次 AI 简历内容");
  } catch (error) {
    showToast("AI 简历历史内容恢复失败，请确认后端已启动");
  } finally {
    resumeDraftHydrating = false;
    resumeDraftState.restoring = false;
  }
}

function exportResumePdf() {
  if (!resumeLab.generated.trim()) {
    showToast("请先生成或编辑简历正文");
    return;
  }
  const printWindow = window.open("", "_blank", "width=920,height=760");
  if (!printWindow) {
    showToast("浏览器拦截了导出窗口，请允许弹窗后重试");
    return;
  }
  const title = `${profile.name || "GradMate"}_申请简历`;
  printWindow.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${title}</title><style>
    @page { size: A4; margin: 16mm; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #202a2a; font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; line-height: 1.7; }
    .resume { max-width: 178mm; margin: 0 auto; }
    .resume-id-photo { float: right; width: 28mm; height: 38mm; object-fit: cover; border-radius: 3px; margin: 0 0 8mm 8mm; }
    h1 { margin: 0 0 6mm; font-size: 22pt; letter-spacing: 1px; }
    h2 { clear: both; margin: 8mm 0 3mm; padding-bottom: 2mm; border-bottom: 1px solid #a9c5bb; color: #175c4b; font-size: 13pt; }
    h3 { margin: 5mm 0 2mm; font-size: 11pt; }
    h4 { margin: 4mm 0 1mm; font-size: 10.5pt; }
    p, li { font-size: 10.5pt; }
    ul { margin: 2mm 0; padding-left: 5mm; }
    .resume-highlight { color: #0f6b53; font-weight: 700; }
    .resume-key-label { font-weight: 700; }
    @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
  </style></head><body><main class="resume">${resumePreviewHtml.value}</main></body></html>`);
  printWindow.document.close();
  printWindow.focus();
  window.setTimeout(() => printWindow.print(), 350);
  showToast("已打开 PDF 导出窗口，请选择“另存为 PDF”完成导出");
}

function loadResumePhoto(event) {
  const file = event.target.files?.[0] || null;
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    showToast("请上传 JPG、PNG 或 WebP 图片");
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    showToast("证件照大小不能超过 2MB");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    resumeLab.photo = String(reader.result || "");
    resumeLab.photoName = file.name;
    showToast("证件照已上传");
  };
  reader.onerror = () => showToast("证件照读取失败，请重新选择");
  reader.readAsDataURL(file);
}

function removeResumePhoto() {
  resumeLab.photo = "";
  resumeLab.photoName = "";
  showToast("证件照已移除");
}

function startResumeProgress() {
  resumeLab.progress = 8;
  const timer = window.setInterval(() => {
    if (!resumeLab.generating) {
      window.clearInterval(timer);
      return;
    }
    resumeLab.progress = Math.min(92, resumeLab.progress + 9);
  }, 420);
}

async function generateResume() {
  if (!canGenerateResume.value) {
    showToast("请先填写画像、目标方向或简历材料");
    return;
  }
  resumeLab.generating = true;
  resumeLab.review = null;
  startResumeProgress();
  showToast("AI 正在生成申请简历...");
  try {
    const result = await api("/api/resume/generate", {
      method: "POST",
      body: JSON.stringify({
        target: resumeLab.target,
        resume_text: resumeLab.sourceText,
        highlights: resumeLab.highlights,
        style: resumeLab.style,
      }),
    });
    resumeLab.generated = result.resume || "";
    resumeLab.sections = result.sections || [];
    resumeLab.suggestions = result.suggestions || [];
    resumeLab.progress = 100;
    showToast("AI 简历已生成");
  } catch (error) {
    showToast(`简历生成失败：${error.message || "请确认后端和模型配置可用"}`);
  } finally {
    resumeLab.generating = false;
  }
}

async function reviewResume() {
  if (!resumeLab.generated.trim()) {
    showToast("请先生成或粘贴简历正文");
    return;
  }
  resumeLab.reviewing = true;
  showToast("AI 正在审查简历质量...");
  try {
    const result = await api("/api/resume/review", {
      method: "POST",
      body: JSON.stringify({
        target: resumeLab.target,
        resume_text: resumeLab.generated,
      }),
    });
    resumeLab.review = result;
    showToast(result.ai_used ? "AI 简历审查已完成" : "已用本地规则完成审查");
  } catch (error) {
    showToast(`简历审查失败：${error.message || "请确认后端和模型配置可用"}`);
  } finally {
    resumeLab.reviewing = false;
  }
}

async function loadRagHistory() {
  ragHistory.loading = true;
  try {
    const result = await api("/api/rag/history?limit=30");
    ragHistory.items = result.items || [];
  } catch (error) {
    notify(error.message || "历史记录加载失败");
  } finally {
    ragHistory.loading = false;
  }
}

async function toggleRagHistory() {
  ragHistory.open = !ragHistory.open;
  if (ragHistory.open) await loadRagHistory();
}

function restoreRagHistory(item) {
  rag.question = item.question || "";
  rag.school = item.school || "";
  rag.college = item.college || "";
  rag.answer = item.answer || "";
  rag.sources = item.sources || [];
  rag.used_browser = !!item.used_browser;
}

function openEmailStudio(item) {
  const generatedDraft = item.draft || {};
  selectedSupervisorId.value = item.id;
  emailDraft.to = item.email || "";
  emailDraft.cc = "";
  emailDraft.subject = item.email_subject || generatedDraft.subject || "";
  setEmailBody(item.email_body || generatedDraft.body || "");
  clearAttachments();
  emailDraft.attachmentNote = item.email_attachment_note || "";
  emailReview.value = item.review || null;
  editorMode.value = "edit";
  activeView.value = "email";
}

function selectEmailSupervisor() {
  const item = supervisors.value.find((entry) => Number(entry.id) === Number(selectedSupervisorId.value));
  if (item) openEmailStudio(item);
}

function startContactDrag(item) {
  contactBoard.draggingId = item.id;
}

function endContactDrag() {
  window.setTimeout(() => {
    if (!contactBoard.updatingId) contactBoard.draggingId = null;
  }, 0);
}

async function moveContactCard(status) {
  const supervisorId = Number(contactBoard.draggingId || 0);
  if (!supervisorId) return;
  if (!CONTACT_MANUAL_STATUSES.has(status)) {
    showToast("这个状态由系统跟进，请拖到后续沟通状态");
    return;
  }
  contactBoard.activeStatus = status;
  contactBoard.updatingId = supervisorId;
  try {
    const result = await api(`/api/supervisors/${supervisorId}/contact-status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    supervisors.value = result.supervisors || supervisors.value;
    showToast(`已移动到「${status}」`);
  } catch (error) {
    showToast(`状态更新失败：${error.message || "请确认后端已启动"}`);
  } finally {
    contactBoard.updatingId = null;
    contactBoard.draggingId = null;
  }
}

function selectContactStatus(status) {
  contactBoard.activeStatus = status;
}

async function changeContactStatus(item, event) {
  contactBoard.draggingId = item.id;
  await moveContactCard(event.target.value);
}

function clearHomepageEmbedTimer() {
  if (homepageEmbedTimer) {
    clearTimeout(homepageEmbedTimer);
    homepageEmbedTimer = null;
  }
}

function prepareHomepagePreview(source) {
  const url = String(source || "").trim();
  homepagePreview.requestId += 1;
  homepagePreview.image = "";
  homepagePreview.error = "";
  homepagePreview.url = url;
  homepagePreview.embedLoaded = false;
  homepagePreview.loading = false;
  clearHomepageEmbedTimer();
  if (!isHttpUrl(url)) {
    homepagePreview.mode = "empty";
    return;
  }
  homepagePreview.mode = "embed";
  const requestId = homepagePreview.requestId;
  homepageEmbedTimer = setTimeout(() => {
    if (requestId !== homepagePreview.requestId || homepagePreview.embedLoaded) return;
    loadHomepageScreenshot(url, "官网内嵌加载超时，已切换为截图预览。");
  }, 4500);
}

function handleHomepageIframeLoad() {
  homepagePreview.embedLoaded = true;
  clearHomepageEmbedTimer();
}

async function loadHomepageScreenshot(source, fallbackReason = "") {
  const url = String(source || "").trim();
  homepagePreview.requestId += 1;
  const requestId = homepagePreview.requestId;
  homepagePreview.image = "";
  homepagePreview.error = fallbackReason;
  homepagePreview.url = url;
  homepagePreview.mode = "screenshot";
  homepagePreview.embedLoaded = false;
  clearHomepageEmbedTimer();
  if (!isHttpUrl(url)) {
    homepagePreview.loading = false;
    return;
  }
  homepagePreview.loading = true;
  try {
    const response = await fetch(`${API_BASE}/api/homepage/screenshot?url=${encodeURIComponent(url)}`);
    const text = await response.text();
    let result = {};
    try {
      result = text ? JSON.parse(text) : {};
    } catch {
      result = {};
    }
    if (!response.ok) {
      throw new Error(result.detail || text || `截图失败：${response.status}`);
    }
    if (requestId !== homepagePreview.requestId) return;
    homepagePreview.image = result.image || "";
    homepagePreview.error = homepagePreview.image ? "" : "截图接口没有返回图片。";
  } catch (error) {
    if (requestId !== homepagePreview.requestId) return;
    homepagePreview.error = error.message || "官网预览截图失败";
  } finally {
    if (requestId === homepagePreview.requestId) {
      homepagePreview.loading = false;
    }
  }
}

function insertEmailSnippet(type) {
  const snippets = {
    greeting: `${selectedSupervisor.value?.name || "老师"}老师：\n\n您好！\n\n`,
    background: `我是${profile.university || "本科院校"}${profile.major || "本科专业"}专业的${profile.name || "同学"}，目前成绩排名为${profile.rank || "待补充"}。`,
    direction: `我关注到您在${selectedSupervisor.value?.direction || "相关研究方向"}方面的研究，与我目前关注的${profile.interests || "研究兴趣"}较为契合。`,
    attachment: `随信附上${attachmentSummary.value || "个人简历和成绩单"}，供您参考。`,
    closing: "感谢您在百忙之中阅读这封邮件，期待您的回复。\n\n此致\n敬礼！",
  };
  const addition = snippets[type] || "";
  setEmailBody(emailDraft.body ? `${emailDraft.body}\n${addition}` : addition);
}

async function generateEmail() {
  if (!selectedSupervisor.value) {
    showToast("请先选择导师");
    return;
  }
  if (emailAiWork.generating) return;
  emailAiWork.generating = true;
  showToast("AI 正在生成邮件草稿...");
  try {
    const result = await api("/api/email/generate", {
      method: "POST",
      body: JSON.stringify({
        supervisor_id: selectedSupervisor.value.id,
        tone: emailTone.value,
      }),
    });
    emailDraft.to = selectedSupervisor.value.email || "";
    emailDraft.subject = result.draft?.subject || "";
    setEmailBody(result.draft?.body || "");
    emailReview.value = result.review || null;
    await refreshAll();
    showToast(result.draft?.ai_used ? "AI 邮件草稿已生成" : `已用本地规则生成：${result.draft?.ai_error || emailAiLabel.value}`);
  } catch (error) {
    showToast(`生成失败：${error.message || "请确认后端已启动且模型配置可用"}`);
  } finally {
    emailAiWork.generating = false;
  }
}

async function reviewEmail() {
  const currentBody = getCurrentEmailBody();
  if (!selectedSupervisor.value || !currentBody) {
    showToast("请先选择导师并填写邮件正文");
    return;
  }
  if (emailAiWork.reviewing) return;
  emailAiWork.reviewing = true;
  showToast("AI 正在审查邮件质量...");
  try {
    const result = await api("/api/email/review", {
      method: "POST",
      body: JSON.stringify({
        supervisor_id: selectedSupervisor.value.id,
        subject: emailDraft.subject,
        body: `${currentBody}${attachmentSummary.value ? `\n\n附件：${attachmentSummary.value}` : ""}`,
      }),
    });
    emailReview.value = result.review || null;
    showToast(result.review?.ai_used ? "AI 邮件质量审查已更新" : `已用本地规则审查：${result.review?.ai_error || emailAiLabel.value}`);
  } catch (error) {
    showToast(`审查失败：${error.message || "请确认后端已启动且模型配置可用"}`);
  } finally {
    emailAiWork.reviewing = false;
  }
}
async function confirmSend() {
  if (!selectedSupervisor.value) return;
  const currentBody = getCurrentEmailBody();
  if (!currentBody) {
    showToast("请先填写邮件正文");
    return;
  }
  emailSendConfirm.body = `${currentBody}${attachmentSummary.value ? `\n\n附件：${attachmentSummary.value}` : ""}`;
  emailSendConfirm.message = "";
  emailSendConfirm.sent = false;
  emailSendConfirm.success = false;
  emailSendConfirm.visible = true;
}

function closeEmailSendPreview() {
  if (emailSendConfirm.sending) return;
  emailSendConfirm.visible = false;
}

async function sendEmailAfterPreview() {
  if (!selectedSupervisor.value || emailSendConfirm.sending) return;
  emailSendConfirm.sending = true;
  emailSendConfirm.sent = false;
  emailSendConfirm.message = "正在读取附件并发送邮件...";
  try {
    const attachmentPayloads = await buildAttachmentPayloads();
    const result = await api("/api/email/send", {
      method: "POST",
      body: JSON.stringify({
        supervisor_id: selectedSupervisor.value.id,
        subject: emailDraft.subject,
        body: emailSendConfirm.body,
        recipient: emailDraft.to,
        cc: emailDraft.cc,
        attachment_note: attachmentSummary.value,
        attachment_files: attachmentFiles.value.map((item) => item.name),
        attachment_payloads: attachmentPayloads,
        attachment_total_size: attachmentTotalSize.value,
        confirmed: true,
      }),
    });
    await refreshAll();
    emailSendConfirm.sent = true;
    emailSendConfirm.success = Boolean(result.sent);
    emailSendConfirm.message = result.message || "邮件已发送";
    showToast(emailSendConfirm.message);
  } catch (error) {
    emailSendConfirm.sent = true;
    emailSendConfirm.success = false;
    emailSendConfirm.message = "确认发送失败，请确认导师邮箱、附件和后端状态";
    showToast(emailSendConfirm.message);
  } finally {
    emailSendConfirm.sending = false;
  }
}

watch(
  () => selectedSupervisor.value?.source || "",
  (source) => {
    prepareHomepagePreview(source);
  },
);

watch(resumeLab, () => {
  scheduleResumeDraftSave();
}, { deep: true });

watch(activeView, async (view, previousView) => {
  if (previousView === "resume") {
    window.clearTimeout(resumeDraftTimer);
    await saveResumeDraft();
  }
  if (view === "resume") {
    await loadResumeDraft();
  }
  if (view === "practice" && !practice.questions.length && !practice.loading) {
    loadPracticeQuestions();
  }
});

onMounted(async () => {
  await refreshAll();
  await fetchDDL(false);
  await fetchKnowledge();
});
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand">
        <div class="brand-mark">GM</div>
        <div>
          <strong>GradMate</strong>
          <span>导师申请工作台</span>
        </div>
      </div>

      <nav class="nav-list">
        <section v-for="group in navGroups" :key="group.title" class="nav-group">
          <h2>{{ group.title }}</h2>
          <button
            v-for="item in group.items"
            :key="item.id"
            class="nav-item"
            :class="{ active: activeView === item.id }"
            type="button"
            @click="activeView = item.id"
          >
            <component :is="item.icon" />
            <span>{{ item.label }}</span>
          </button>
        </section>
      </nav>

      <div class="sidebar-note">
        <span class="status-dot" :class="{ offline: !backendOnline }"></span>
        <span>{{ backendOnline ? "服务已连接：http://127.0.0.1:8000" : "服务未连接" }}</span>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">研究生申请 · 导师筛选 · 时间管理</p>
          <h1>{{ viewTitle }}</h1>
        </div>
        <button class="icon-button" type="button" @click="activeView === 'ddl' ? fetchDDL(true) : refreshAll()">
          <RefreshCw />
          <span>刷新</span>
        </button>
      </header>

      <section v-show="activeView === 'dashboard'" class="view">
        <div class="stat-grid">
          <article class="stat-card">
            <div class="stat-icon"><UsersRound /></div>
            <span>导师库</span>
            <strong>{{ dashboard.supervisor_count }}</strong>
            <p>已导入导师资料</p>
          </article>
          <article class="stat-card">
            <div class="stat-icon accent"><BadgeCheck /></div>
            <span>高匹配</span>
            <strong>{{ dashboard.high_match_count }}</strong>
            <p>A 级推荐</p>
          </article>
          <article class="stat-card">
            <div class="stat-icon warn"><MailWarning /></div>
            <span>缺少邮箱</span>
            <strong>{{ dashboard.missing_email_count }}</strong>
            <p>需要人工补充</p>
          </article>
          <article class="stat-card">
            <div class="stat-icon slate"><CalendarClock /></div>
            <span>近期待办</span>
            <strong>{{ ddl.stats.urgent }}</strong>
            <p>7 天内截止通知</p>
          </article>
        </div>

        <div class="dashboard-grid">
          <section class="panel">
            <div class="panel-heading">
              <h2>申请流程</h2>
              <span class="tag">当前阶段</span>
            </div>
            <div class="flow-line">
              <div class="flow-step done"><CircleUserRound /><span>完善画像</span></div>
              <div class="flow-step done"><Upload /><span>导入导师</span></div>
              <div class="flow-step active-step"><ScanSearch /><span>匹配排序</span></div>
              <div class="flow-step"><MailPlus /><span>准备邮件</span></div>
              <div class="flow-step"><Kanban /><span>跟进进度</span></div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <h2>下一步建议</h2>
              <span class="tag muted">自动更新</span>
            </div>
            <ul class="task-list">
              <li v-for="item in nextActions" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>
      </section>

      <section v-show="activeView === 'practice'" class="view">
        <section class="panel practice-hero">
          <div>
            <span class="eyebrow">Question Practice</span>
            <h2>题库练习</h2>
            <p>完成题目后提交，即可查看客观题得分、正确答案与解析；简答题提供参考答案用于自查。</p>
          </div>
          <div class="practice-toolbar">
            <label>题目主题
              <select v-model="practice.topicId" :disabled="practice.loading" @change="loadPracticeQuestions">
                <option v-for="topic in practice.topics" :key="topic.id" :value="topic.id">{{ topic.name }}（{{ topic.question_count }} 题）</option>
              </select>
            </label>
            <button class="inline-button" type="button" :disabled="practice.loading" @click="loadPracticeQuestions">
              <RefreshCw /><span>换一组题</span>
            </button>
          </div>
        </section>

        <div v-if="practice.loading" class="empty-state">正在加载题目……</div>
        <div v-else-if="!practice.questions.length" class="empty-state">当前主题暂无题目。</div>
        <section v-else class="practice-list">
          <article v-for="(item, index) in practice.questions" :key="item.id" class="panel practice-question">
            <div class="practice-question-head">
              <span class="question-number">{{ index + 1 }}</span>
              <div>
                <div class="practice-tags"><span class="tag">{{ item.type === 'essay' ? '简答题' : '单选题' }}</span><span class="tag muted">{{ item.difficulty === 'hard' ? '困难' : item.difficulty === 'medium' ? '中等' : '简单' }}</span><span v-for="tag in item.tags" :key="tag.id" class="tag muted">{{ tag.name }}</span></div>
                <h2>{{ item.title }}</h2>
              </div>
            </div>

            <p v-if="item.content" class="practice-content">{{ item.content }}</p>

            <textarea v-if="item.type === 'essay'" v-model="practice.answers[item.id]" class="practice-essay" :disabled="practice.submitted" placeholder="请输入你的答案……"></textarea>
            <div v-else class="practice-options">
              <label v-for="option in item.choices" :key="option.label" class="practice-option" :class="{ selected: practice.answers[item.id] === option.label, correct: practice.submitted && practiceResultMap[item.id]?.correct_answer === option.label, wrong: practice.submitted && practice.answers[item.id] === option.label && !practiceResultMap[item.id]?.correct }">
                <input v-model="practice.answers[item.id]" :disabled="practice.submitted" type="radio" :name="`practice-${item.id}`" :value="option.label" />
                <strong>{{ option.label }}</strong><span>{{ option.text }}</span>
              </label>
            </div>

            <div v-if="practice.submitted && practiceResultMap[item.id]" class="practice-feedback" :class="{ success: practiceResultMap[item.id].correct, neutral: item.type === 'essay' }">
              <strong v-if="item.type !== 'essay'">{{ practiceResultMap[item.id].correct ? '回答正确' : `正确答案：${practiceResultMap[item.id].correct_answer}` }}</strong>
              <strong v-else>参考答案</strong>
              <p v-if="item.type === 'essay'">{{ practiceResultMap[item.id].reference_answer }}</p>
              <p>{{ practiceResultMap[item.id].explanation }}</p>
            </div>
          </article>
          <section class="panel practice-submit">
            <div><strong>完成进度：{{ Object.values(practice.answers).filter(Boolean).length }} / {{ practice.questions.length }}</strong><p v-if="practice.submitted">本次客观题得分：{{ practice.result?.score }} 分（{{ practice.result?.objective_correct }} / {{ practice.result?.objective_total }}）</p></div>
            <button class="primary-button" type="button" :disabled="practice.submitted" @click="submitPracticeAnswers"><BadgeCheck /><span>{{ practice.submitted ? '已提交' : '提交并查看答案' }}</span></button>
          </section>
        </section>
      </section>

      <section v-show="activeView === 'assistant'" class="view">
        <div class="assistant-layout">
          <section class="panel assistant-workbench">
            <div class="panel-heading compact-heading">
              <h2>GradMate 智能申请助理</h2>
              <span class="tag">多工具协同</span>
              <button class="inline-button history-toggle" type="button" :disabled="assistantHistory.loading" @click="toggleAssistantHistory">
                <Eye />
                <span>{{ assistantHistory.open ? "收起历史记录" : "查看历史记录" }}</span>
              </button>
            </div>
            <p class="assistant-intro">用自然语言描述申请目标，助理会读取画像、检索导师与招生资料、计算匹配，并按需生成和审查邮件草稿。</p>
            <label class="assistant-input">
              <span>申请任务</span>
              <textarea v-model="applicationAssistant.message" rows="6" placeholder="例如：根据我的个人背景，筛选人工智能相关导师并生成联系邮件。"></textarea>
            </label>
            <button class="primary-button assistant-run" type="button" :disabled="applicationAssistant.loading" @click="runApplicationAssistant">
              <Bot />
              <span>{{ applicationAssistant.loading ? "正在执行任务链" : "执行申请任务" }}</span>
            </button>

            <section v-if="assistantHistory.open" class="assistant-history">
              <div class="panel-heading compact-heading">
                <h2>历史申请任务</h2>
                <span class="tag muted">{{ assistantHistory.items.length }} 条</span>
              </div>
              <div v-if="assistantHistory.loading" class="empty-state small">历史记录加载中。</div>
              <div v-else-if="!assistantHistory.items.length" class="empty-state small">暂时还没有已完成的智能申请任务。</div>
              <div v-else class="history-list">
                <button v-for="item in assistantHistory.items" :key="item.id" class="history-item" type="button" @click="restoreAssistantHistory(item)">
                  <span class="history-time">{{ item.created_at }}</span>
                  <strong>{{ item.message }}</strong>
                  <span>推荐 {{ item.recommendations?.length || 0 }} 位导师 · {{ item.events?.length || 0 }} 个执行事件</span>
                </button>
              </div>
            </section>

            <section v-if="applicationAssistant.answer" class="assistant-answer">
              <div class="panel-heading compact-heading">
                <h2>执行结果</h2>
                <span class="tag muted">已保存草稿</span>
              </div>
              <p>{{ applicationAssistant.answer }}</p>
            </section>

            <div v-if="applicationAssistant.recommendations.length" class="assistant-recommendations">
              <article v-for="item in applicationAssistant.recommendations" :key="item.id" class="assistant-recommendation">
                <div class="recommendation-header">
                  <div>
                    <strong>{{ item.name }}</strong>
                    <span>{{ [item.school, item.college].filter(Boolean).join(" / ") || "院校信息待补充" }}</span>
                  </div>
                  <b>{{ item.score }} 分</b>
                </div>
                <p><span>研究方向：</span>{{ item.direction || "待补充" }}</p>
                <p><span>推荐理由：</span>{{ item.reason }}</p>
                <p v-if="item.risk"><span>核验提示：</span>{{ item.risk }}</p>
                <div class="recommendation-footer">
                  <span v-if="item.draft" class="tag">邮件草稿已保存</span>
                  <span v-if="item.review?.score" class="tag muted">审查 {{ item.review.score }} 分</span>
                  <button class="inline-button compact-button" type="button" @click="openEmailStudio(item)">
                    <MailPlus /><span>查看邮件</span>
                  </button>
                </div>
              </article>
            </div>

            <section v-if="applicationAssistant.admission_sources.length" class="assistant-sources">
              <div class="panel-heading compact-heading"><h2>检索到的招生资料</h2></div>
              <article v-for="(item, index) in applicationAssistant.admission_sources" :key="`${item.source}-${index}`">
                <strong>{{ item.source }}</strong>
                <span class="tag muted">{{ item.kind }}</span>
                <p>{{ item.snippet }}</p>
              </article>
            </section>
          </section>

          <aside class="panel assistant-trace" aria-live="polite">
            <div class="panel-heading compact-heading">
              <h2>执行过程</h2>
              <span class="tag muted">事件流</span>
            </div>
            <div v-if="!applicationAssistant.events.length" class="empty-state small">提交任务后，这里会展示 Agent 的工具调用过程。</div>
            <ol v-else class="assistant-event-list">
              <li v-for="(item, index) in applicationAssistant.events" :key="`${item.time}-${index}`" :class="item.event">
                <span class="event-dot"></span>
                <div>
                  <div class="event-topline"><strong>{{ item.name }}</strong><time>{{ item.time }}</time></div>
                  <p>{{ item.message }}</p>
                  <small v-if="item.detail">{{ item.detail }}</small>
                </div>
              </li>
            </ol>
          </aside>
        </div>
      </section>

      <section v-show="activeView === 'profile'" class="view">
        <div class="profile-layout">
          <form class="panel" @submit.prevent="saveProfile">
            <div class="panel-heading">
              <h2>学生画像</h2>
              <span class="tag">基础信息</span>
            </div>
            <div class="form-grid">
              <label>姓名<input v-model="profile.name" placeholder="例如：张同学" /></label>
              <label>本科院校<input v-model="profile.university" placeholder="例如：清华大学" /></label>
              <label>本科专业<input v-model="profile.major" placeholder="例如：软件工程" /></label>
              <label>成绩排名<input v-model="profile.rank" placeholder="例如：前 2%" /></label>
              <label class="span-2">研究兴趣<input v-model="profile.interests" placeholder="可信 AI、联邦学习、机器学习安全" /></label>
              <label class="span-2">项目经历<input v-model="profile.projects" placeholder="联邦学习、视觉模型、数据分析" /></label>
              <label>英语水平<input v-model="profile.english" placeholder="CET-6 520" /></label>
              <label>申请类型
                <select v-model="profile.application_type">
                  <option>保研</option>
                  <option>考研</option>
                  <option>夏令营</option>
                </select>
              </label>
              <label>目标学校<input v-model="profile.target_schools" placeholder="清华大学、北京大学" /></label>
              <label>目标学院<input v-model="profile.target_colleges" placeholder="人工智能学院、软件学院" /></label>
            </div>
            <button class="primary-button" type="submit"><Save /><span>保存画像</span></button>
          </form>

          <aside class="summary-panel">
            <div class="panel-heading">
              <h2>画像摘要</h2>
              <span class="tag muted">已保存内容</span>
            </div>
            <p>{{ profileSummary }}</p>
          </aside>
        </div>
      </section>

      <section v-show="activeView === 'resume'" class="view">
        <section class="panel email-context-panel resume-context-panel">
          <div class="email-context-main">
            <div class="email-context-copy">
              <span class="tag">申请材料</span>
              <h2>AI 简历工作台</h2>
              <p>参考个人画像、目标导师方向和已有材料，生成适合保研、夏令营、预推免或导师联系的中文简历。</p>
            </div>
          </div>
          <div class="email-context-metrics">
            <div><span>栏目</span><strong>{{ resumeLab.sections.length || "-" }}</strong></div>
            <div><span>进度</span><strong>{{ resumeLab.generating ? `${resumeLab.progress}%` : "待生成" }}</strong></div>
            <div><span>质量分</span><strong>{{ resumeLab.review?.score || "-" }}</strong></div>
          </div>
          <button class="primary-button resume-generate-button" type="button" :disabled="resumeLab.generating || !canGenerateResume" @click="generateResume">
            <LoaderCircle v-if="resumeLab.generating" class="spin-icon" />
            <Sparkles v-else />
            <span>{{ resumeLab.generating ? "AI 生成中" : "AI 一键生成简历" }}</span>
          </button>
        </section>

        <div class="email-layout resume-layout">
          <section class="panel email-editor compose-panel resume-input-panel">
            <div class="composer-head">
              <div>
                <h2>输入材料</h2>
                <p>填写目标方向、已有材料和希望突出的亮点，AI 会整理为结构化申请简历。</p>
              </div>
              <span class="tag muted">{{ resumeLab.style }}</span>
            </div>
            <div class="form-grid">
              <div class="resume-photo-card span-2">
                <div>
                  <strong>证件照</strong>
                  <span>{{ resumeLab.photoName || "支持 JPG / PNG / WebP，建议使用清晰正面照" }}</span>
                </div>
                <label class="resume-photo-uploader">
                  <img v-if="resumeLab.photo" :src="resumeLab.photo" alt="证件照预览" />
                  <span v-else>上传证件照</span>
                  <input type="file" accept="image/png,image/jpeg,image/jpg,image/webp" @change="loadResumePhoto" />
                </label>
                <button v-if="resumeLab.photo" class="inline-button compact-button" type="button" @click="removeResumePhoto">
                  <Eraser />
                  <span>移除照片</span>
                </button>
              </div>
              <label class="span-2">目标方向 / 导师要求 / JD
                <input v-model="resumeLab.target" placeholder="例如：可信 AI、联邦学习、导师课题组方向或夏令营要求" />
              </label>
              <label>简历风格
                <select v-model="resumeLab.style">
                  <option>保研导师联系</option>
                  <option>夏令营申请</option>
                  <option>预推免材料</option>
                  <option>科研助理申请</option>
                </select>
              </label>
              <label class="resume-file-picker">上传简历文件
                <span class="resume-file-drop">
                  <UploadCloud />
                  <strong>{{ resumeLab.uploadName || "选择或拖入简历文件" }}</strong>
                  <small>支持 TXT / MD / CSV / PDF，PDF 会自动提取文字</small>
                </span>
                <input type="file" accept=".txt,.md,.csv,.pdf,application/pdf" @change="loadResumeSourceFile" />
              </label>
              <label class="span-2">希望突出的亮点
                <textarea v-model="resumeLab.highlights" placeholder="例如：排名、科研训练、项目贡献、竞赛、英语、代码能力、论文阅读经历"></textarea>
              </label>
              <label class="span-2">已有简历 / 补充材料
                <textarea v-model="resumeLab.sourceText" placeholder="可粘贴旧简历、项目说明、获奖经历。上传文件后文本也会出现在这里。"></textarea>
              </label>
            </div>
            <div v-if="resumeLab.generating" class="ai-progress">
              <div><span>AI 正在分析画像与材料</span><strong>{{ resumeLab.progress }}%</strong></div>
              <span :style="{ width: `${resumeLab.progress}%` }"></span>
            </div>
            <div class="resume-actions">
              <button class="inline-button" type="button" :disabled="resumeLab.reviewing || !resumeLab.generated" @click="reviewResume">
                <LoaderCircle v-if="resumeLab.reviewing" class="spin-icon" />
                <MailCheck v-else />
                <span>{{ resumeLab.reviewing ? "审查中" : "AI 质量审查" }}</span>
              </button>
              <button class="inline-button" type="button" @click="resumeLab.generated = ''; resumeLab.review = null">
                <Eraser />
                <span>清空结果</span>
              </button>
            </div>
          </section>

          <aside class="summary-panel review-panel resume-side-panel">
            <section class="inspector-card">
              <div class="panel-heading">
                <h2>生成建议</h2>
                <span class="tag muted">{{ resumeLab.sections.length || 0 }} 项栏目</span>
              </div>
              <ul class="task-list" v-if="resumeLab.suggestions.length">
                <li v-for="item in resumeLab.suggestions" :key="item">{{ item }}</li>
              </ul>
              <p v-else>生成后会在这里显示 AI 对内容补充、栏目调整和目标匹配的建议。</p>
            </section>
            <section class="inspector-card">
              <div class="panel-heading">
                <h2>质量审查</h2>
                <span class="tag muted">{{ resumeLab.review ? `${resumeLab.review.score || 0} 分` : "待审查" }}</span>
              </div>
              <template v-if="resumeLab.review">
                <ul class="check-list">
                  <li v-for="item in resumeLab.review.checks" :key="item.label" :class="{ passed: item.passed }">
                    {{ item.passed ? "通过" : "待补充" }}：{{ item.label }}
                  </li>
                </ul>
              </template>
              <p v-else>生成简历后点击“AI 质量审查”，系统会检查结构完整度、目标契合和科研表达。</p>
            </section>
          </aside>
        </div>

        <section class="panel email-editor compose-panel resume-preview-panel">
          <div class="composer-head">
            <div>
              <h2>简历预览</h2>
              <p>左侧可继续编辑 Markdown 正文，右侧实时显示投递前预览。</p>
            </div>
            <div class="toolbar-actions">
              <span class="tag muted">{{ resumeDraftState.restoring ? "正在恢复" : (resumeLab.uploadName || "Markdown 预览") }}</span>
              <button class="inline-button compact-button" type="button" :disabled="!resumeLab.generated" @click="exportResumePdf">
                <Download />
                <span>导出 PDF</span>
              </button>
            </div>
          </div>
          <div class="resume-preview-grid">
            <textarea v-model="resumeLab.generated" placeholder="AI 生成的简历正文可在这里继续编辑。"></textarea>
            <article class="resume-paper-preview" v-html="resumePreviewHtml"></article>
          </div>
        </section>
      </section>

      <section v-show="activeView === 'documents'" class="view">
        <div class="upload-layout">
          <section class="panel">
            <div class="panel-heading">
              <h2>导师资料上传</h2>
              <span class="tag">文本 / 表格</span>
            </div>
            <div class="upload-form">
              <label>资料来源<input v-model="sourceInput" placeholder="例如：学院官网 / 招生简章 PDF" /></label>
              <label>上传资料文件<input ref="supervisorFileInput" type="file" accept=".txt,.csv,.tsv,.md,.pdf,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @change="loadFile" /></label>
              <label class="span-2">
                粘贴导师资料
                <textarea
                  v-model="supervisorText"
                  placeholder="支持 CSV/TSV 表格，或按段粘贴：姓名：陈教授&#10;学校：吉林大学&#10;学院：人工智能学院&#10;研究方向：可信 AI、机器学习安全&#10;邮箱：chen@example.edu.cn&#10;招生类型：保研"
                ></textarea>
              </label>
            </div>
            <button class="primary-button" type="button" :disabled="browserSearch.loading" @click="uploadSupervisors"><UploadCloud /><span>{{ browserSearch.loading ? "上传中" : "上传并抽取" }}</span></button>
          </section>

          <aside class="summary-panel">
            <div class="panel-heading">
              <h2>抽取结果说明</h2>
              <span class="tag muted">导师库</span>
            </div>
            <p>系统会抽取导师姓名、学校、学院、职称、研究方向、邮箱、招生类型和来源。缺失字段不会被编造，会在匹配结果中提示风险。</p>
          </aside>
        </div>

        <section class="panel browser-panel">
          <div class="panel-heading">
            <h2>官网自动检索</h2>
            <span class="tag">Agent 浏览器工具</span>
          </div>
          <div class="browser-grid">
            <label>学校<input v-model="browserSearch.school" placeholder="例如：吉林大学" /></label>
            <label>专业关键词<input v-model="browserSearch.major" placeholder="例如：软件工程、计算机科学与技术" /></label>
            <label>学院关键词<input v-model="browserSearch.college" placeholder="例如：软件学院、人工智能学院" /></label>
            <label>补充关键词<input v-model="browserSearch.keywords" placeholder="例如：研究生导师、师资队伍" /></label>
            <label>浏览页数
              <select class="legacy-page-select" v-model.number="browserSearch.max_pages">
                <option :value="3">3 页</option>
                <option :value="5">5 页</option>
                <option :value="8">8 页</option>
                <option :value="12">12 页</option>
              </select>
              <input v-model.number="browserSearch.max_pages" type="number" min="1" max="30" step="1" />
            </label>
            <button class="primary-button browser-action" type="button" :disabled="browserSearch.loading" @click="browseSupervisorSites">
              <Globe2 />
              <span>{{ browserSearch.loading ? "检索中" : "检索官网并导入" }}</span>
            </button>
          </div>
          <div v-if="browserSearch.visited_pages.length || browserSearch.trace.length" class="trace-toggle-row">
            <span>已访问 {{ browserSearch.visited_pages.length }} 页，导入 {{ browserSearch.imported }} 条</span>
            <button class="inline-button compact-button" type="button" @click="browserSearch.showTrace = !browserSearch.showTrace">
              <span>{{ browserSearch.showTrace ? "收起流程" : "查看检索流程" }}</span>
            </button>
          </div>
          <div v-if="browserSearch.showTrace && browserSearch.visited_pages.length" class="visited-list">
            <a
              v-for="page in browserSearch.visited_pages"
              :key="page.url"
              :href="page.url"
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink />
              <span>{{ page.title || page.url }}</span>
            </a>
          </div>
          <ol v-if="browserSearch.showTrace && browserSearch.trace.length" class="trace-list">
            <li v-for="item in browserSearch.trace" :key="item">{{ item }}</li>
          </ol>
        </section>

        <section class="panel table-panel">
          <div class="panel-heading">
            <h2>导师信息表</h2>
            <span class="tag muted">{{ supervisors.length }} 条</span>
            <div class="export-actions">
              <button class="inline-button compact-button" type="button" :disabled="!supervisors.length" @click="exportGet('/api/export/supervisors', 'docx')">
                <Download /><span>Word</span>
              </button>
              <button class="inline-button compact-button" type="button" :disabled="!supervisors.length" @click="exportGet('/api/export/supervisors', 'xlsx')">
                <FileSpreadsheet /><span>Excel</span>
              </button>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>导师</th>
                  <th>学校</th>
                  <th>学院</th>
                  <th>方向</th>
                  <th>邮箱</th>
                  <th>来源</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in pagedDocumentSupervisors" :key="item.id">
                  <td>{{ item.name || "待确认" }}</td>
                  <td>{{ item.school || "-" }}</td>
                  <td>{{ item.college || "-" }}</td>
                  <td>{{ item.direction || "-" }}</td>
                  <td><span v-if="!item.email" class="pill warning">缺失</span><span v-else>{{ item.email }}</span></td>
                  <td>
                    <a
                      v-if="isHttpUrl(item.source)"
                      class="source-link"
                      :href="item.source"
                      target="_blank"
                      rel="noreferrer"
                      :title="item.source"
                    >
                      <ExternalLink />
                      <span>{{ item.source }}</span>
                    </a>
                    <span v-else>{{ item.source || "-" }}</span>
                  </td>
                  <td>
                    <div class="table-actions">
                    <button class="inline-button" type="button" @click="openEmailStudio(item)">
                      <MailPlus />
                      <span>发邮件</span>
                    </button>
                    <button
                      class="danger-icon-button"
                      type="button"
                      title="删除导师资料"
                      aria-label="删除导师资料"
                      @click="deleteSupervisor(item)"
                    >
                      <Trash2 />
                    </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="latestSupervisors.length" class="pagination-bar">
            <span>第 {{ documentPager.page }} / {{ documentTotalPages }} 页，共 {{ latestSupervisors.length }} 条</span>
            <div class="pagination-actions">
              <button class="inline-button compact-button" type="button" :disabled="documentPager.page <= 1" @click="documentPager.page -= 1">上一页</button>
              <button class="inline-button compact-button" type="button" :disabled="documentPager.page >= documentTotalPages" @click="documentPager.page += 1">下一页</button>
            </div>
          </div>
        </section>
      </section>

      <section v-show="activeView === 'matching'" class="view">
        <section class="panel match-toolbar">
          <div>
            <div class="panel-heading compact-heading">
              <h2>导师匹配</h2>
              <span class="tag">按画像排序</span>
            </div>
            <p>{{ profileSummary || "匹配会使用当前保存的个人画像。" }}</p>
          </div>
          <div class="toolbar-actions">
            <div class="export-actions">
              <button class="inline-button compact-button" type="button" :disabled="!supervisors.length" @click="exportGet('/api/export/matches', 'docx')">
                <Download /><span>Word</span>
              </button>
              <button class="inline-button compact-button" type="button" :disabled="!supervisors.length" @click="exportGet('/api/export/matches', 'xlsx')">
                <FileSpreadsheet /><span>Excel</span>
              </button>
            </div>
            <button class="primary-button" type="button" @click="matchSupervisors"><Sparkles /><span>计算匹配评分</span></button>
          </div>
        </section>

        <section class="panel filter-panel">
          <label class="search-field">
            关键词
            <span>
              <Search />
              <input v-model="matchingFilters.query" placeholder="导师、学校、方向、邮箱" @input="resetMatchingPage" />
            </span>
          </label>
          <label>匹配等级
            <select v-model="matchingFilters.level" @change="resetMatchingPage">
              <option value="">全部</option>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="C">C</option>
              <option value="未评估">未评估</option>
            </select>
          </label>
          <label>邮箱状态
            <select v-model="matchingFilters.email" @change="resetMatchingPage">
              <option value="">全部</option>
              <option value="has">有邮箱</option>
              <option value="missing">缺少邮箱</option>
            </select>
          </label>
          <label>排序方式
            <select v-model="matchingSort" @change="resetMatchingPage">
              <option value="newest">最新添加</option>
              <option value="score">匹配分从高到低</option>
            </select>
          </label>
        </section>

        <div class="mentor-grid">
          <div v-if="!supervisors.length" class="empty-state">请先上传导师资料。</div>
          <div v-else-if="!filteredMatchingSupervisors.length" class="empty-state">没有符合筛选条件的导师。</div>
          <article v-for="item in pagedMatchingSupervisors" v-else :key="item.id" class="mentor-card">
            <div class="mentor-score">{{ item.match_score || 0 }}</div>
            <h2>{{ item.name || "待确认导师" }} <span class="pill muted">{{ item.match_level || "未评分" }}</span></h2>
            <p>{{ [item.school, item.college].filter(Boolean).join(" / ") || "院校待确认" }}</p>
            <strong>{{ item.direction || "研究方向待补充" }}</strong>
            <p>{{ item.match_reason || "点击“计算匹配评分”后生成推荐理由。" }}</p>
            <p v-if="item.match_breakdown" class="match-breakdown">
              混合排序：文本向量 {{ Math.round(item.match_breakdown.text_vector || 0) }} ·
              方向 {{ Math.round(item.match_breakdown.direction_overlap || 0) }} ·
              项目 {{ Math.round(item.match_breakdown.project_relevance || 0) }} ·
              数据质量 {{ Math.round(item.match_breakdown.data_quality || 0) }}
            </p>
            <p>{{ item.risk_note || "风险提示将在评分后生成。" }}</p>
            <button class="inline-button" type="button" @click="openEmailStudio(item)">
              <MailPlus />
              <span>生成邮件</span>
            </button>
          </article>
        </div>
        <div v-if="filteredMatchingSupervisors.length" class="pagination-bar matching-pagination">
          <span>第 {{ matchingPager.page }} / {{ matchingTotalPages }} 页，共 {{ filteredMatchingSupervisors.length }} 位导师</span>
          <div class="pagination-actions">
            <label class="page-size-select">
              <span>每页</span>
              <select v-model.number="matchingPager.pageSize" @change="resetMatchingPage">
                <option :value="6">6</option>
                <option :value="12">12</option>
                <option :value="24">24</option>
              </select>
            </label>
            <button class="inline-button compact-button" type="button" :disabled="matchingPager.page <= 1" @click="matchingPager.page -= 1">上一页</button>
            <button class="inline-button compact-button" type="button" :disabled="matchingPager.page >= matchingTotalPages" @click="matchingPager.page += 1">下一页</button>
          </div>
        </div>
      </section>

      <section v-show="activeView === 'contact'" class="view">
        <section class="panel contact-board-hero">
          <div>
            <div class="panel-heading compact-heading">
              <h2>联系进度看板</h2>
              <span class="tag">联系状态</span>
            </div>
            <p>拖动导师卡片到上方状态，即可更新后续联系进度。</p>
          </div>
          <div class="contact-board-stats">
            <div><span>导师数</span><strong>{{ contactStats.total }}</strong></div>
            <div><span>已发送</span><strong>{{ contactStats.sent }}</strong></div>
            <div><span>等待回复</span><strong>{{ contactStats.waiting }}</strong></div>
            <div><span>后续跟进</span><strong>{{ contactStats.manual }}</strong></div>
          </div>
        </section>

        <section class="panel contact-status-strip" aria-label="联系状态筛选">
          <button
            v-for="group in contactStatusGroups"
            :key="group.status"
            class="contact-status-chip"
            :class="{ active: contactBoard.activeStatus === group.status, manual: !group.auto, 'drop-target': contactBoard.draggingId && !group.auto }"
            type="button"
            @click="selectContactStatus(group.status)"
            @dragover.prevent
            @drop="moveContactCard(group.status)"
          >
            <span>{{ group.status }}</span>
            <strong>{{ group.count }}</strong>
          </button>
        </section>

        <section
          class="panel contact-focus-panel"
          :class="{ 'drop-ready': contactBoard.draggingId && !activeContactGroup.auto }"
          @dragover.prevent
          @drop="moveContactCard(activeContactGroup.status)"
        >
          <div class="contact-focus-head">
            <div>
              <h2>{{ activeContactGroup.status }}</h2>
              <p>拖动导师卡片到上方状态胶囊，或在卡片右侧直接修改状态。</p>
            </div>
            <strong>{{ activeContactGroup.items.length }} 位导师</strong>
          </div>

          <div class="contact-list">
            <article
              v-for="item in activeContactGroup.items"
              :key="item.id"
              class="contact-card contact-row-card"
              :class="{ updating: contactBoard.updatingId === item.id }"
              draggable="true"
              @dragstart="startContactDrag(item)"
              @dragend="endContactDrag"
            >
              <span class="contact-drag-handle" title="拖动调整状态">⋮⋮</span>
              <div class="contact-card-main">
                <div class="contact-card-title">
                  <strong>{{ item.name || "待确认导师" }}</strong>
                  <span class="pill muted">{{ getContactStatus(item) }}</span>
                </div>
                <p>{{ [item.school, item.college].filter(Boolean).join(" / ") || "院校待确认" }}</p>
                <p class="contact-direction">{{ item.direction || "研究方向待补充" }}</p>
              </div>
              <div class="contact-card-meta">
                <span>上次联系</span>
                <strong>{{ getContactDate(item) || "暂无记录" }}</strong>
              </div>
              <p class="contact-advice">{{ contactSuggestion(item) }}</p>
              <div class="contact-card-actions">
                <select :value="getContactStatus(item)" :disabled="contactBoard.updatingId === item.id" @change="changeContactStatus(item, $event)">
                  <option value="未联系" disabled>未联系</option>
                  <option value="已生成草稿" disabled>已生成草稿</option>
                  <option value="已发送" disabled>已发送</option>
                  <option v-for="status in CONTACT_STATUSES.slice(3)" :key="status" :value="status">{{ status }}</option>
                </select>
                <button class="inline-button compact-button" type="button" @click="openEmailStudio(item)">
                  <MailPlus />
                  <span>去写邮件</span>
                </button>
              </div>
            </article>
            <div v-if="!activeContactGroup.items.length" class="contact-empty">当前状态暂无导师。</div>
          </div>
        </section>
      </section>

      <section v-show="activeView === 'email'" class="view">
        <section class="panel email-context-panel">
          <div class="email-context-main">
            <label>当前导师
              <select v-model="selectedSupervisorId" @change="selectEmailSupervisor">
                <option :value="null" disabled>请选择导师</option>
                <option v-for="item in supervisors" :key="item.id" :value="item.id">
                  {{ item.name || "待确认导师" }} · {{ item.email || "邮箱待补充" }}
                </option>
              </select>
            </label>
            <div class="email-context-copy">
              <span class="tag">{{ selectedSupervisor ? getContactStatus(selectedSupervisor) : "未联系" }}</span>
              <h2>{{ selectedMentorMeta.title }}</h2>
              <p>{{ selectedMentorMeta.subtitle }} · {{ selectedMentorMeta.direction }}</p>
            </div>
          </div>
          <div class="email-context-metrics">
            <div><span>匹配度</span><strong>{{ selectedMentorMeta.score }}</strong></div>
            <div><span>完成度</span><strong>{{ emailReadiness.score }}%</strong></div>
            <div><span>质量分</span><strong>{{ emailReview?.score || "-" }}</strong></div>
          </div>
        </section>

        <section class="panel smtp-config-panel">
          <div class="panel-heading">
            <div>
              <h2>发件服务状态</h2>
              <p>{{ emailSmtpDetail }}</p>
            </div>
            <span class="tag" :class="{ muted: !emailSmtpConfig.smtp_configured }">{{ emailSmtpLabel }}</span>
          </div>
          <div class="smtp-options-row">
            <span class="tag muted">{{ emailSmtpConfig.smtp_use_ssl ? "SSL" : emailSmtpConfig.smtp_use_tls ? "STARTTLS" : "未加密" }}</span>
            <span>为避免在公开部署中泄露凭据，账号与授权码仅可通过服务端环境变量配置。</span>
          </div>
        </section>

        <div class="email-layout">
          <section class="panel email-editor compose-panel">
            <div class="composer-head">
              <div>
                <h2>邮件编辑器</h2>
                <p>{{ selectedSupervisor ? "撰写导师联系邮件" : "请选择导师" }}</p>
              </div>
              <div class="composer-actions">
                <button class="icon-button compact-action" type="button" :disabled="emailAiWork.reviewing || emailAiWork.generating" @click="reviewEmail">
                  <LoaderCircle v-if="emailAiWork.reviewing" class="spin-icon" />
                  <MailCheck v-else />
                  <span>{{ emailAiWork.reviewing ? "审查中" : "质量审查" }}</span>
                </button>
                <button class="primary-button compact-action" type="button" :disabled="emailAiWork.generating || emailAiWork.reviewing" @click="generateEmail">
                  <LoaderCircle v-if="emailAiWork.generating" class="spin-icon" />
                  <Sparkles v-else />
                  <span>{{ emailAiWork.generating ? "生成中" : "生成草稿" }}</span>
                </button>
              </div>
            </div>

            <div class="composer-toolbar">
              <div class="segmented-control" aria-label="编辑模式">
                <button type="button" :class="{ active: editorMode === 'edit' }" @click="editorMode = 'edit'">
                  <TextCursorInput />
                  <span>编辑</span>
                </button>
                <button type="button" :class="{ active: editorMode === 'preview' }" @click="editorMode = 'preview'">
                  <Eye />
                  <span>预览</span>
                </button>
              </div>
              <div class="email-stats">
                <span>{{ emailStats.chars }} 字</span>
                <span>{{ emailStats.paragraphs }} 段</span>
                <span>{{ emailStats.lines }} 行</span>
              </div>
            </div>

            <div class="message-fields">
              <label class="field-card">收件人
                <input v-model="emailDraft.to" placeholder="导师邮箱" />
              </label>
              <label class="field-card">抄送
                <input v-model="emailDraft.cc" placeholder="可选，例如自己的邮箱" />
              </label>
              <label class="field-card span-2">主题
                <input v-model="emailDraft.subject" placeholder="邮件主题" />
              </label>
            </div>

            <div class="assistant-strip">
              <label>AI 版本
                <select v-model="emailTone">
                  <option>正式版</option>
                  <option>简洁版</option>
                </select>
              </label>
              <div class="assistant-copy">
                <strong :class="{ online: emailAiStatus.ready, warning: !emailAiStatus.ready }">{{ emailAiLabel }}</strong>
                <span>{{ emailAiDetail }}</span>
              </div>
            </div>

            <div class="snippet-bar" aria-label="常用片段">
              <button type="button" @click="insertEmailSnippet('greeting')">称呼</button>
              <button type="button" @click="insertEmailSnippet('background')">背景</button>
              <button type="button" @click="insertEmailSnippet('direction')">方向契合</button>
              <button type="button" @click="insertEmailSnippet('attachment')">附件</button>
              <button type="button" @click="insertEmailSnippet('closing')">结尾</button>
            </div>

            <label v-show="editorMode === 'edit'" class="editor-block">
              正文编辑区
              <div class="rich-toolbar" aria-label="富文本工具栏">
                <button type="button" title="加粗" @click="applyRichCommand('bold')"><Bold /></button>
                <button type="button" title="斜体" @click="applyRichCommand('italic')"><Italic /></button>
                <button type="button" title="下划线" @click="applyRichCommand('underline')"><Underline /></button>
                <button type="button" title="无序列表" @click="applyRichCommand('insertUnorderedList')"><ListFilter /></button>
                <button type="button" title="有序列表" @click="applyRichCommand('insertOrderedList')"><ListOrdered /></button>
                <button type="button" title="清除格式" @click="applyRichCommand('removeFormat')"><Eraser /></button>
              </div>
              <div
                ref="richEditor"
                class="rich-editor"
                contenteditable="true"
                role="textbox"
                aria-multiline="true"
                data-placeholder="在这里写邮件正文。可以先点“生成草稿”，再手动加粗重点经历、调整研究方向、补充附件说明和结尾。"
                @input="syncRichEditor"
                @blur="syncRichEditor"
              ></div>
            </label>

            <div v-show="editorMode === 'preview'" class="mail-preview">
              <div class="preview-row"><span>To</span><strong>{{ emailDraft.to || "未填写收件人" }}</strong></div>
              <div class="preview-row" v-if="emailDraft.cc"><span>Cc</span><strong>{{ emailDraft.cc }}</strong></div>
              <div class="preview-row"><span>Subject</span><strong>{{ emailDraft.subject || "未填写主题" }}</strong></div>
              <div class="preview-content" v-html="emailPreviewHtml"></div>
            </div>

            <div class="send-row">
              <div>
                <strong>发送确认</strong>
                <p>点击后会先进入最终预览，确认后通过已配置的 SMTP 账号真实发送。</p>
              </div>
              <button class="primary-button" type="button" :disabled="!selectedSupervisor || !emailDraft.to || !emailDraft.subject || !hasEmailBody" @click="confirmSend">
                <Send />
                <span>确认发送</span>
              </button>
            </div>
          </section>

          <aside class="summary-panel review-panel email-inspector">
            <section class="inspector-card homepage-preview-card">
              <div class="panel-heading">
                <h2>导师主页</h2>
                <a
                  v-if="selectedSupervisor && isHttpUrl(selectedSupervisor.source)"
                  class="ddl-link"
                  :href="selectedSupervisor.source"
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink />
                  <span>打开</span>
                </a>
                <span v-else class="tag muted">暂无主页</span>
              </div>
              <div v-if="selectedSupervisor && isHttpUrl(selectedSupervisor.source)" class="homepage-preview-box">
                <div v-if="homepagePreview.mode === 'embed'" class="homepage-embed-wrap">
                  <iframe
                    :key="homepagePreview.url"
                    class="homepage-iframe"
                    :src="homepagePreview.url"
                    title="导师官网内嵌预览"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    @load="handleHomepageIframeLoad"
                  ></iframe>
                  <div v-if="!homepagePreview.embedLoaded" class="homepage-preview-loading homepage-embed-loading">
                    <LoaderCircle class="spin-icon" />
                    <span>正在尝试内嵌官网</span>
                  </div>
                </div>
                <div v-else-if="homepagePreview.loading" class="homepage-preview-loading">
                  <LoaderCircle class="spin-icon" />
                  <span>正在截取官网首屏</span>
                </div>
                <img v-else-if="homepagePreview.image" :src="homepagePreview.image" alt="导师官网预览截图" />
                <div v-else class="homepage-link-card">
                  <Globe2 />
                  <div>
                    <strong>官网截图暂不可用</strong>
                    <p>{{ homepagePreview.error || "学校官网可能加载较慢，或本机浏览器驱动不可用。" }}</p>
                  </div>
                </div>
                <div class="homepage-preview-caption">
                  <span>{{ selectedSupervisor.source }}</span>
                  <button
                    v-if="homepagePreview.mode === 'embed'"
                    class="text-button"
                    type="button"
                    @click="loadHomepageScreenshot(selectedSupervisor.source, '已手动切换为截图预览。')"
                  >
                    截图预览
                  </button>
                </div>
              </div>
              <p v-else>当前导师没有可预览的官网来源。可以先在“导师资料”里用官网自动检索补充来源。</p>
            </section>

            <section class="inspector-card">
              <div class="panel-heading">
                <h2>发送摘要</h2>
                <span class="tag muted">{{ emailReadiness.score }}%</span>
              </div>
              <div class="readiness-meter"><span :style="{ width: `${emailReadiness.score}%` }"></span></div>
              <ul class="readiness-list">
                <li v-for="item in emailReadiness.checks" :key="item.label" :class="{ done: item.done }">
                  <span></span>{{ item.label }}
                </li>
              </ul>
              <div class="attachment-upload compact-upload">
                <div class="attachment-upload-head">
                  <div>
                    <strong>附件上传</strong>
                    <span>单个 {{ formatFileSize(MAX_ATTACHMENT_FILE_SIZE) }} / 总计 {{ formatFileSize(MAX_ATTACHMENT_TOTAL_SIZE) }}</span>
                  </div>
                  <button class="inline-button" type="button" :disabled="!attachmentFiles.length && !emailDraft.attachmentNote" @click="clearEmailAttachments">
                    <Eraser />
                    <span>清空</span>
                  </button>
                </div>
                <label class="attachment-dropzone">
                  <UploadCloud />
                  <span>选择附件</span>
                  <input
                    :key="attachmentInputVersion"
                    type="file"
                    multiple
                    accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                    @change="handleAttachmentUpload"
                  />
                </label>
                <ul v-if="attachmentFiles.length" class="attachment-list">
                  <li v-for="(file, index) in attachmentFiles" :key="`${file.name}-${file.size}`">
                    <span>{{ file.name }}</span>
                    <strong>{{ formatFileSize(file.size) }}</strong>
                    <button class="danger-icon-button compact-delete" type="button" title="删除附件" @click="removeAttachment(index)">
                      <Trash2 />
                    </button>
                  </li>
                </ul>
                <p v-else-if="emailDraft.attachmentNote">{{ emailDraft.attachmentNote }}</p>
                <p v-else>尚未选择附件。</p>
              </div>
            </section>

            <section class="inspector-card">
              <div class="panel-heading">
                <h2>质量审查</h2>
                <span class="tag muted">{{ emailReview ? `${emailReview.score} 分` : "待审查" }}</span>
              </div>
              <template v-if="emailReview">
                <ul class="check-list">
                  <li v-for="item in emailReview.checks" :key="item.label" :class="{ passed: item.passed }">
                    {{ item.passed ? "通过" : "待补充" }}：{{ item.label }}
                  </li>
                </ul>
                <div class="review-suggestions">
                  <strong>建议</strong>
                  <p v-for="item in emailReview.suggestions" :key="item">{{ item }}</p>
                </div>
              </template>
              <p v-else>生成草稿或编辑后点击“质量审查”，系统会检查称呼、方向匹配、附件说明和主题明确度。</p>
            </section>
          </aside>
        </div>
      </section>

      <section v-show="activeView === 'rag'" class="view">
        <section class="panel rag-layout">
          <div>
            <div class="panel-heading compact-heading">
              <h2>招生简章问答</h2>
              <span class="tag">RAG 知识库</span>
            </div>
            <p>上传招生简章、学院通知或导师介绍后，系统将基于来源内容回答问题。</p>
            <button class="inline-button history-toggle" type="button" :disabled="ragHistory.loading" @click="toggleRagHistory">
              <Eye />
              <span>{{ ragHistory.open ? "收起历史记录" : "查看历史记录" }}</span>
            </button>
          </div>
          <div class="rag-upload">
            <label>资料类型
              <select v-model="rag.kind">
                <option>招生简章</option>
                <option>学院通知</option>
                <option>导师介绍</option>
              </select>
            </label>
            <label>上传文件
              <input type="file" accept=".pdf,.txt,.md,.csv,.tsv,application/pdf" @change="loadKnowledgeFile" />
            </label>
            <button class="primary-button" type="button" :disabled="rag.uploading" @click="uploadKnowledge">
              <UploadCloud />
              <span>{{ rag.uploading ? "入库中" : "上传入库" }}</span>
            </button>
          </div>
        </section>

        <section class="panel rag-ask">
          <div class="form-grid">
            <label>学校关键词<input v-model="rag.school" placeholder="例如：清华大学" /></label>
            <label>学院关键词<input v-model="rag.college" placeholder="例如：计算机学院" /></label>
            <label class="span-2">问题<input v-model="rag.question" placeholder="例如：这个学院推免需要英语成绩吗？" @keyup.enter="askRag" /></label>
          </div>
          <label class="checkbox-row">
            <input v-model="rag.use_browser" type="checkbox" />
            <span>知识库不足时自动检索网页和学院通知</span>
          </label>
          <button class="primary-button" type="button" :disabled="rag.asking" @click="askRag">
            <Search />
            <span>{{ rag.asking ? "查询中" : "提问" }}</span>
          </button>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <h2>知识库</h2>
            <span class="tag muted">{{ rag.knowledge.chunk_count || 0 }} 个片段</span>
          </div>
          <div v-if="rag.knowledge.files?.length" class="knowledge-files">
            <span v-for="item in rag.knowledge.files" :key="item.source" class="tag">{{ item.source }} · {{ item.chunks }} 片段</span>
          </div>
          <div v-else class="empty-state small">还没有上传招生资料。</div>
        </section>

        <section v-if="rag.answer" class="panel rag-answer">
          <div class="panel-heading">
            <h2>回答</h2>
            <span class="tag" :class="{ muted: !rag.used_browser }">{{ rag.used_browser ? "含网页检索" : "知识库回答" }}</span>
            <div class="export-actions">
              <button class="inline-button compact-button" type="button" @click="exportRagAnswer('docx')"><Download /><span>Word</span></button>
              <button class="inline-button compact-button" type="button" @click="exportRagAnswer('xlsx')"><FileSpreadsheet /><span>Excel</span></button>
            </div>
          </div>
          <article class="answer-text rag-markdown" v-html="ragAnswerHtml"></article>
          <div class="source-list">
            <article v-for="(item, index) in rag.sources" :key="index" class="source-card">
              <strong>[{{ index + 1 }}] {{ item.source }}</strong>
              <span class="tag muted">{{ item.kind }}</span>
              <p>{{ item.snippet }}</p>
            </article>
          </div>
        </section>

        <section v-if="ragHistory.open" class="panel history-panel">
          <div class="panel-heading">
            <h2>问答历史记录</h2>
            <span class="tag muted">{{ ragHistory.items.length }} 条</span>
          </div>
          <div v-if="ragHistory.loading" class="empty-state small">历史记录加载中。</div>
          <div v-else-if="!ragHistory.items.length" class="empty-state small">暂时还没有问答历史记录。</div>
          <div v-else class="history-list">
            <button v-for="item in ragHistory.items" :key="item.id" class="history-item" type="button" @click="restoreRagHistory(item)">
              <span class="history-time">{{ item.created_at }}</span>
              <strong>{{ item.question }}</strong>
              <span>{{ [item.school, item.college].filter(Boolean).join(" / ") || "未指定院校" }}</span>
            </button>
          </div>
        </section>
      </section>

      <section v-show="activeView === 'questions'" class="view">
        <section class="panel question-toolbar">
          <div>
            <div class="panel-heading compact-heading">
              <h2>可能问题生成</h2>
              <span class="tag">大模型辅助</span>
            </div>
            <p>结合学生画像、项目经历和导师研究方向，生成可能被追问的问题。</p>
          </div>
          <div class="toolbar-actions">
            <button class="inline-button history-toggle" type="button" :disabled="questionHistory.loading" @click="toggleQuestionHistory">
              <Eye />
              <span>{{ questionHistory.open ? "收起历史记录" : "查看历史记录" }}</span>
            </button>
            <button class="primary-button" type="button" :disabled="questionLab.loading" @click="generateQuestions">
              <Sparkles />
              <span>{{ questionLab.loading ? "生成中" : "生成问题" }}</span>
            </button>
          </div>
        </section>

        <section class="panel question-form">
          <label>选择导师
            <select v-model.number="questionLab.supervisor_id">
              <option value="">请选择导师</option>
              <option v-for="item in supervisors" :key="item.id" :value="item.id">{{ item.name || "待确认导师" }} - {{ [item.school, item.college].filter(Boolean).join(" / ") || "院校待确认" }}</option>
            </select>
          </label>
          <label class="span-2">关注点
            <input v-model="questionLab.focus" placeholder="例如：联邦学习项目、科研经历薄弱、跨专业申请" />
          </label>
        </section>

        <section v-if="questionLab.result" class="panel question-result">
          <div class="panel-heading">
            <h2>{{ questionLab.result.supervisor || "目标导师" }}</h2>
            <span class="tag muted">问题清单</span>
            <div class="export-actions">
              <button class="inline-button compact-button" type="button" @click="exportQuestionResult('docx')"><Download /><span>Word</span></button>
              <button class="inline-button compact-button" type="button" @click="exportQuestionResult('xlsx')"><FileSpreadsheet /><span>Excel</span></button>
            </div>
          </div>
          <p>{{ questionLab.result.summary }}</p>
          <div class="question-groups">
            <article v-for="group in questionLab.result.groups" :key="group.title" class="question-group">
              <h2>{{ group.title }}</h2>
              <div v-for="item in group.items" :key="item.question" class="question-item">
                <strong>{{ item.question }}</strong>
                <p><span>考察点：</span>{{ item.intent }}</p>
                <p><span>准备提示：</span>{{ item.prep }}</p>
              </div>
            </article>
          </div>
        </section>
        <div v-else class="empty-state small">选择导师后生成可能问题。</div>

        <section v-if="questionHistory.open" class="panel history-panel">
          <div class="panel-heading">
            <h2>问题生成历史</h2>
            <span class="tag muted">{{ questionHistory.items.length }} 条</span>
          </div>
          <div v-if="questionHistory.loading" class="empty-state small">历史记录加载中。</div>
          <div v-else-if="!questionHistory.items.length" class="empty-state small">暂时还没有问题生成记录。</div>
          <div v-else class="history-list">
            <button v-for="item in questionHistory.items" :key="item.id" class="history-item" type="button" @click="restoreQuestionHistory(item)">
              <span class="history-time">{{ item.created_at }}</span>
              <strong>{{ item.supervisor_name || "目标导师" }}</strong>
              <span>{{ item.focus || "未填写额外关注点" }}</span>
            </button>
          </div>
        </section>
      </section>

      <section v-show="activeView === 'ddl'" class="view">
        <section class="panel ddl-toolbar">
          <div>
            <div class="panel-heading compact-heading">
              <h2>招生通知</h2>
              <span class="tag">{{ ddl.source_label }}</span>
            </div>
          </div>
          <div class="ddl-controls">
            <label>
              数据源
              <select v-model="ddl.source" @change="fetchDDL(false)">
                <option v-for="item in ddl.sources" :key="item.id" :value="item.id">{{ item.label }}</option>
              </select>
            </label>
            <label class="search-field">
              关键词
              <span>
                <Search />
                <input v-model="ddl.query" placeholder="学校、学院、方向" @keyup.enter="fetchDDL(false)" />
              </span>
            </label>
            <div class="export-actions">
              <button class="inline-button compact-button" type="button" :disabled="!ddl.items.length" @click="exportDdl('docx')">
                <Download /><span>Word</span>
              </button>
              <button class="inline-button compact-button" type="button" :disabled="!ddl.items.length" @click="exportDdl('xlsx')">
                <FileSpreadsheet /><span>Excel</span>
              </button>
            </div>
            <button class="icon-button" type="button" :disabled="ddl.loading" @click="fetchDDL(true)">
              <RefreshCw />
              <span>{{ ddl.loading ? "加载中" : "更新" }}</span>
            </button>
          </div>
        </section>

        <div class="ddl-stats">
          <article class="stat-card">
            <div class="stat-icon"><CalendarClock /></div>
            <span>通知总数</span>
            <strong>{{ ddl.stats.total }}</strong>
            <p>当前筛选结果</p>
          </article>
          <article class="stat-card">
            <div class="stat-icon warn"><CalendarClock /></div>
            <span>即将截止</span>
            <strong>{{ ddl.stats.urgent }}</strong>
            <p>7 天内</p>
          </article>
          <article class="stat-card">
            <div class="stat-icon accent"><BadgeCheck /></div>
            <span>报名中</span>
            <strong>{{ ddl.stats.upcoming }}</strong>
            <p>仍可准备</p>
          </article>
          <article class="stat-card">
            <div class="stat-icon slate"><FilePenLine /></div>
            <span>已截止</span>
            <strong>{{ ddl.stats.closed }}</strong>
            <p>可作参考</p>
          </article>
        </div>

        <div class="ddl-list">
          <div v-if="!ddl.items.length" class="empty-state">暂无匹配的招生通知。</div>
          <article v-for="item in pagedDdlItems" v-else :key="`${item.name}-${item.institute}-${item.deadline}`" class="ddl-card">
            <div class="ddl-main">
              <div class="ddl-title-row">
                <span class="status-badge" :class="item.status">{{ statusText(item.status) }}</span>
                <strong>{{ item.name }}</strong>
              </div>
              <p class="ddl-meta">{{ [item.institute, item.province].filter(Boolean).join(" · ") || "单位待确认" }}</p>
              <p class="ddl-description">{{ item.description || "暂无补充说明" }}</p>
              <div class="ddl-tags">
                <span v-for="tag in item.tags.slice(0, 4)" :key="tag" class="pill muted">{{ tag }}</span>
              </div>
            </div>
            <div class="ddl-side">
              <span class="ddl-date">{{ item.deadline_date || "日期待确认" }}</span>
              <strong>{{ daysText(item) }}</strong>
              <a v-if="item.website" class="ddl-link" :href="item.website" target="_blank" rel="noreferrer">
                <ExternalLink />
                <span>查看通知</span>
              </a>
            </div>
          </article>
        </div>
        <div v-if="ddl.items.length" class="pagination-bar ddl-pagination">
          <span>共 {{ ddl.items.length }} 条通知，第 {{ ddlPager.page }} / {{ ddlTotalPages }} 页</span>
          <div class="pagination-actions">
            <label class="page-size-select">
              <span>每页</span>
              <select v-model.number="ddlPager.pageSize" @change="resetDdlPage">
                <option :value="10">10</option>
                <option :value="20">20</option>
                <option :value="30">30</option>
              </select>
            </label>
            <button class="inline-button compact-button" type="button" :disabled="ddlPager.page <= 1" @click="ddlPager.page -= 1">上一页</button>
            <button class="inline-button compact-button" type="button" :disabled="ddlPager.page >= ddlTotalPages" @click="ddlPager.page += 1">下一页</button>
          </div>
        </div>
      </section>
    </main>
  </div>

  <div v-if="emailSendConfirm.visible" class="modal-backdrop" role="dialog" aria-modal="true" aria-label="邮件最终预览">
    <section class="modal-panel email-confirm-modal">
      <div class="modal-head">
        <div>
          <h2>{{ emailSendConfirm.sent ? "发送结果" : "最终预览确认" }}</h2>
          <p>{{ emailSendConfirm.sent ? emailSendConfirm.message : "请确认收件人、主题、正文和附件，确认后会真实发送邮件。" }}</p>
        </div>
        <button class="icon-button compact-action" type="button" :disabled="emailSendConfirm.sending" @click="closeEmailSendPreview">
          <span>关闭</span>
        </button>
      </div>

      <div class="email-confirm-status" v-if="emailSendConfirm.sent" :class="{ success: emailSendConfirm.success }">
        <BadgeCheck v-if="emailSendConfirm.success" />
        <MailWarning v-else />
        <span>{{ emailSendConfirm.message }}</span>
      </div>

      <div class="email-confirm-meta">
        <div><span>发件服务</span><strong>{{ emailSmtpConfig.smtp_configured ? "服务端已配置" : "未配置" }}</strong></div>
        <div><span>收件人</span><strong>{{ emailDraft.to }}</strong></div>
        <div v-if="emailDraft.cc"><span>抄送</span><strong>{{ emailDraft.cc }}</strong></div>
        <div><span>主题</span><strong>{{ emailDraft.subject }}</strong></div>
      </div>

      <div class="email-confirm-body">
        <span>正文预览</span>
        <pre>{{ emailSendConfirm.body }}</pre>
      </div>

      <div class="email-confirm-attachments">
        <span>附件</span>
        <ul v-if="attachmentFiles.length">
          <li v-for="file in attachmentFiles" :key="`${file.name}-${file.size}`">
            <span>{{ file.name }}</span>
            <strong>{{ formatFileSize(file.size) }}</strong>
          </li>
        </ul>
        <p v-else>无附件</p>
      </div>

      <div class="modal-actions">
        <button class="inline-button" type="button" :disabled="emailSendConfirm.sending" @click="closeEmailSendPreview">
          <span>{{ emailSendConfirm.sent ? "完成" : "返回修改" }}</span>
        </button>
        <button
          v-if="!emailSendConfirm.sent"
          class="primary-button"
          type="button"
          :disabled="emailSendConfirm.sending"
          @click="sendEmailAfterPreview"
        >
          <LoaderCircle v-if="emailSendConfirm.sending" class="spin-icon" />
          <Send v-else />
          <span>{{ emailSendConfirm.sending ? "发送中" : "确认发送" }}</span>
        </button>
      </div>
    </section>
  </div>

  <div class="toast" :class="{ show: toastVisible }" role="status" aria-live="polite">{{ toast }}</div>
</template>


