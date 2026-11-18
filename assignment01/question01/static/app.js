(() => {
  "use strict";

  const state = {
    jobId: null,
    job: null,
    timer: null,
    polling: false,
    previewSignature: "",
    logsSignature: "",
    failuresSignature: "",
    activeTab: "results",
  };

  const statusLabels = {
    queued: "排队中",
    running: "运行中",
    paused: "已暂停",
    stopping: "停止中",
    stopped: "已停止",
    completed: "已完成",
    failed: "失败",
  };

  const activeStatuses = new Set(["queued", "running", "paused", "stopping"]);

  const el = {
    form: document.getElementById("crawlForm"),
    startUrl: document.getElementById("startUrl"),
    maxPages: document.getElementById("maxPages"),
    requestInterval: document.getElementById("requestInterval"),
    fetchDetails: document.getElementById("fetchDetails"),
    startBtn: document.getElementById("startBtn"),
    pauseBtn: document.getElementById("pauseBtn"),
    resumeBtn: document.getElementById("resumeBtn"),
    stopBtn: document.getElementById("stopBtn"),
    formMessage: document.getElementById("formMessage"),
    statusPill: document.getElementById("statusPill"),
    statusMessage: document.getElementById("statusMessage"),
    progressFill: document.getElementById("progressFill"),
    metricPages: document.getElementById("metricPages"),
    metricCurrentPage: document.getElementById("metricCurrentPage"),
    metricRecords: document.getElementById("metricRecords"),
    metricQuality: document.getElementById("metricQuality"),
    metricQualityNote: document.getElementById("metricQualityNote"),
    metricElapsed: document.getElementById("metricElapsed"),
    metricJobId: document.getElementById("metricJobId"),
    downloadRow: document.getElementById("downloadRow"),
    downloadCsv: document.getElementById("downloadCsv"),
    downloadJson: document.getElementById("downloadJson"),
    downloadLog: document.getElementById("downloadLog"),
    previewCount: document.getElementById("previewCount"),
    resultsBody: document.getElementById("resultsBody"),
    logTerminal: document.getElementById("logTerminal"),
    failureList: document.getElementById("failureList"),
    failureTabCount: document.getElementById("failureTabCount"),
    tabButtons: [...document.querySelectorAll(".tab-button")],
    tabPanels: [...document.querySelectorAll(".tab-panel")],
  };

  function formatApiError(payload) {
    if (!payload) return "请求失败";
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item.msg || JSON.stringify(item)).join("；");
    }
    return JSON.stringify(payload);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(formatApiError(payload) || `HTTP ${response.status}`);
    }
    return response.json();
  }

  function setFormMessage(text, isError = false) {
    el.formMessage.textContent = text;
    el.formMessage.classList.toggle("error", isError);
  }

  function safeHttpUrl(raw) {
    try {
      const url = new URL(raw);
      return url.protocol === "https:" ? url.href : null;
    } catch {
      return null;
    }
  }

  function statusClass(status) {
    return ["queued", "running", "paused", "stopping", "stopped", "completed", "failed"].includes(status)
      ? status
      : "idle";
  }

  function durationText(startedAt, finishedAt) {
    if (!startedAt) return "00:00";
    const start = new Date(startedAt).getTime();
    const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
    if (!Number.isFinite(start) || !Number.isFinite(end)) return "00:00";
    const total = Math.max(0, Math.floor((end - start) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    const pair = (value) => String(value).padStart(2, "0");
    return hours > 0 ? `${pair(hours)}:${pair(minutes)}:${pair(seconds)}` : `${pair(minutes)}:${pair(seconds)}`;
  }

  function updateButtons(job) {
    const status = job?.status || "idle";
    const active = activeStatuses.has(status);
    el.startBtn.disabled = active;
    el.pauseBtn.disabled = status !== "running";
    el.resumeBtn.disabled = status !== "paused";
    el.stopBtn.disabled = !new Set(["queued", "running", "paused"]).has(status);
  }

  function applyJob(job) {
    state.jobId = job.id;
    state.job = job;
    const status = job.status || "queued";
    el.statusPill.textContent = statusLabels[status] || status;
    el.statusPill.className = `status-pill ${statusClass(status)}`;
    el.statusMessage.textContent = job.message || "等待任务状态更新";
    el.statusMessage.classList.toggle("safety", job.pause_reason === "safety");

    const progress = Math.max(0, Math.min(100, Number(job.progress_percent) || 0));
    el.progressFill.style.width = `${progress}%`;
    el.metricPages.textContent = `${job.pages_done || 0} / ${job.pages_total || 0}`;
    el.metricCurrentPage.textContent = job.current_page
      ? `当前页：${job.current_page}`
      : status === "completed" ? "全部页码已完成" : "当前页：—";
    el.metricRecords.textContent = String(job.records_count || 0);
    el.metricQuality.textContent = `${job.duplicates_count || 0} / ${job.failures_count || 0}`;
    el.metricElapsed.textContent = durationText(job.started_at, job.finished_at);
    el.metricJobId.textContent = `任务 ID：${String(job.id).slice(0, 18)}…`;
    el.metricJobId.title = job.id;
    el.failureTabCount.textContent = String(job.failures_count || 0);
    el.downloadRow.hidden = false;

    const prefix = `/api/jobs/${encodeURIComponent(job.id)}`;
    el.downloadCsv.href = `${prefix}/result.csv`;
    el.downloadJson.href = `${prefix}/result.json`;
    el.downloadLog.href = `${prefix}/run.log`;
    updateButtons(job);
  }

  function resetIdleView() {
    state.jobId = null;
    state.job = null;
    el.statusPill.textContent = "空闲";
    el.statusPill.className = "status-pill idle";
    el.statusMessage.textContent = "尚未启动任务。设置参数后点击“启动任务”。";
    el.statusMessage.classList.remove("safety");
    el.progressFill.style.width = "0%";
    el.metricPages.textContent = "0 / 0";
    el.metricCurrentPage.textContent = "当前页：—";
    el.metricRecords.textContent = "0";
    el.metricQuality.textContent = "0 / 0";
    el.metricElapsed.textContent = "00:00";
    el.metricJobId.textContent = "任务 ID：—";
    el.downloadRow.hidden = true;
    updateButtons(null);
  }

  function emptyTable(text) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.textContent = text;
    row.appendChild(cell);
    el.resultsBody.replaceChildren(row);
  }

  function cell(text, className = "") {
    const td = document.createElement("td");
    td.textContent = text ?? "";
    if (className) td.className = className;
    return td;
  }

  function renderPreview(items, total) {
    el.previewCount.textContent = `${total} 条预览`;
    if (!items.length) {
      emptyTable("任务已启动，但还没有可展示的记录。");
      return;
    }
    const fragment = document.createDocumentFragment();
    items.forEach((item, index) => {
      const row = document.createElement("tr");
      row.appendChild(cell(String(index + 1)));
      row.appendChild(cell(item.title, "title-cell"));
      row.appendChild(cell(item.price));
      row.appendChild(cell("★".repeat(item.rating || 0), "rating"));
      row.appendChild(cell(item.category || "—"));
      row.appendChild(cell(item.availability || "—"));
      row.appendChild(cell(item.description || "—", "description-cell"));
      const linkCell = document.createElement("td");
      const link = document.createElement("a");
      const href = safeHttpUrl(item.detail_url);
      if (href) {
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "打开";
        linkCell.appendChild(link);
      } else {
        linkCell.textContent = "—";
      }
      row.appendChild(linkCell);
      fragment.appendChild(row);
    });
    el.resultsBody.replaceChildren(fragment);
  }

  function renderLogs(logs) {
    if (!logs.length) {
      const empty = document.createElement("div");
      empty.className = "terminal-empty";
      empty.textContent = "暂无日志。";
      el.logTerminal.replaceChildren(empty);
      return;
    }
    const nearBottom =
      el.logTerminal.scrollHeight - el.logTerminal.scrollTop - el.logTerminal.clientHeight < 70;
    const fragment = document.createDocumentFragment();
    logs.forEach((entry) => {
      const line = document.createElement("div");
      line.className = "terminal-line";
      const time = document.createElement("span");
      time.className = "terminal-time";
      time.textContent = new Date(entry.created_at).toLocaleString("zh-CN", { hour12: false });
      const level = document.createElement("span");
      level.className = `terminal-level ${String(entry.level).toLowerCase()}`;
      level.textContent = entry.level;
      const message = document.createElement("span");
      message.className = "terminal-message";
      message.textContent = entry.message;
      line.append(time, level, message);
      fragment.appendChild(line);
    });
    el.logTerminal.replaceChildren(fragment);
    if (nearBottom || state.job?.status === "running") {
      el.logTerminal.scrollTop = el.logTerminal.scrollHeight;
    }
  }

  function renderFailures(failures) {
    el.failureTabCount.textContent = String(failures.length);
    if (!failures.length) {
      const empty = document.createElement("p");
      empty.className = "empty-copy";
      empty.textContent = "暂无失败记录。";
      el.failureList.replaceChildren(empty);
      return;
    }
    const fragment = document.createDocumentFragment();
    failures.forEach((failure) => {
      const card = document.createElement("article");
      card.className = "failure-card";
      const main = document.createElement("div");
      const heading = document.createElement("h4");
      heading.textContent = `${failure.error_type}${failure.http_status ? ` · HTTP ${failure.http_status}` : ""}`;
      const message = document.createElement("p");
      message.textContent = failure.message;
      main.append(heading, message);
      const meta = document.createElement("div");
      const time = document.createElement("div");
      time.className = "failure-time";
      time.textContent = new Date(failure.created_at).toLocaleString("zh-CN", { hour12: false });
      const link = document.createElement("a");
      const href = safeHttpUrl(failure.source_url);
      if (href) {
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = failure.source_url;
      } else {
        link.textContent = String(failure.source_url).slice(0, 90);
      }
      meta.append(time, link);
      card.append(main, meta);
      fragment.appendChild(card);
    });
    el.failureList.replaceChildren(fragment);
  }

  function setActiveTab(name) {
    state.activeTab = name;
    el.tabButtons.forEach((button) => {
      const selected = button.dataset.tab === name;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-selected", String(selected));
    });
    el.tabPanels.forEach((panel) => {
      const selected = panel.id === `panel${name.charAt(0).toUpperCase()}${name.slice(1)}`;
      panel.hidden = !selected;
      panel.classList.toggle("active", selected);
    });
  }

  async function refreshJobData() {
    if (!state.jobId) return;
    const jobId = state.jobId;
    const prefix = `/api/jobs/${encodeURIComponent(jobId)}`;
    const [job, preview, logs, failures] = await Promise.all([
      api(prefix),
      api(`${prefix}/preview?limit=120`),
      api(`${prefix}/logs?limit=300`),
      api(`${prefix}/failures`),
    ]);
    if (state.jobId !== jobId) return;
    applyJob(job);

    const previewSignature = `${preview.total}:${preview.items.map((item) => item.id).join(",")}`;
    if (previewSignature !== state.previewSignature) {
      state.previewSignature = previewSignature;
      renderPreview(preview.items, preview.total);
    }

    const logsSignature = logs.length ? String(logs[logs.length - 1].id) : "0";
    if (logsSignature !== state.logsSignature) {
      state.logsSignature = logsSignature;
      renderLogs(logs);
    }

    const failuresSignature = failures.length ? String(failures[0].id) : "0";
    if (failuresSignature !== state.failuresSignature) {
      state.failuresSignature = failuresSignature;
      renderFailures(failures);
    }
  }

  async function poll() {
    if (state.polling || !state.jobId) return;
    state.polling = true;
    try {
      await refreshJobData();
    } catch (error) {
      setFormMessage(`状态刷新失败：${error.message}`, true);
    } finally {
      state.polling = false;
    }
  }

  function beginPolling() {
    if (state.timer) window.clearInterval(state.timer);
    state.timer = window.setInterval(poll, 1000);
  }

  async function action(path, successText) {
    if (!state.jobId) return;
    const buttons = [el.pauseBtn, el.resumeBtn, el.stopBtn];
    buttons.forEach((button) => { button.disabled = true; });
    try {
      const job = await api(`/api/jobs/${encodeURIComponent(state.jobId)}${path}`, { method: "POST" });
      applyJob(job);
      setFormMessage(successText);
      await poll();
    } catch (error) {
      setFormMessage(error.message, true);
      updateButtons(state.job);
    }
  }

  el.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormMessage("正在创建任务…");
    el.startBtn.disabled = true;
    try {
      const payload = {
        start_url: el.startUrl.value.trim(),
        max_pages: Number(el.maxPages.value),
        request_interval: Number(el.requestInterval.value),
        fetch_details: el.fetchDetails.checked,
      };
      const job = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
      state.previewSignature = "";
      state.logsSignature = "";
      state.failuresSignature = "";
      applyJob(job);
      renderLogs([]);
      renderFailures([]);
      emptyTable("任务已启动，正在等待第一条记录…");
      setFormMessage(`任务 ${job.id} 已启动`);
      await poll();
    } catch (error) {
      setFormMessage(error.message, true);
      updateButtons(state.job);
    }
  });

  el.pauseBtn.addEventListener("click", () => action("/pause", "暂停请求已发送，worker 会在安全点停下"));
  el.resumeBtn.addEventListener("click", () => action("/resume", "任务已继续"));
  el.stopBtn.addEventListener("click", () => action("/stop", "停止请求已发送"));

  el.tabButtons.forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
  });

  async function initialize() {
    setActiveTab("results");
    try {
      const latest = await api("/api/jobs/latest");
      if (latest?.id) {
        applyJob(latest);
        emptyTable("正在载入最近任务的数据…");
        await refreshJobData();
      } else {
        resetIdleView();
      }
    } catch (error) {
      resetIdleView();
      setFormMessage(`无法连接后端：${error.message}`, true);
    }
    beginPolling();
  }

  initialize();
})();
