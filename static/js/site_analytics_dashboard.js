(() => {
  const periodUnit = document.getElementById("analytics-period-unit");
  const rangeFields = document.querySelectorAll("[data-range-fields]");
  const periodCount = document.getElementById("analytics-period-count");
  const moreFilters = document.getElementById("analytics-more-filters");
  const moreFiltersState = document.getElementById("analytics-more-filters-state");

  function updateRangeFields() {
    const mode = periodUnit?.value === "custom" ? "custom" : "period";
    rangeFields.forEach((field) => {
      const active = field.dataset.rangeFields === mode;
      field.hidden = !active;
      if (field instanceof HTMLFieldSetElement) field.disabled = !active;
      field.querySelectorAll("input, select").forEach((control) => {
        control.disabled = !active;
      });
    });
    if (periodCount && periodUnit) {
      const maxCount = ({ days: "365", weeks: "104", months: "60", years: "5" })[periodUnit.value] || "365";
      periodCount.max = maxCount;
      if (Number(periodCount.value) > Number(maxCount)) periodCount.value = maxCount;
    }
  }

  periodUnit?.addEventListener("change", updateRangeFields);
  moreFilters?.addEventListener("toggle", () => {
    if (moreFiltersState) moreFiltersState.value = moreFilters.open ? "1" : "0";
  });
  updateRangeFields();

  const journeyForm = document.getElementById("analytics-journey-filter");
  const journeyPages = document.getElementById("analytics-journey-pages");
  const journeyDepth = document.getElementById("analytics-journey-depth");
  const journeyTemplate = document.getElementById("analytics-journey-page-template");
  const addJourneyPage = document.getElementById("analytics-add-journey-page");
  const journeyStatus = document.getElementById("analytics-journey-expand-status");

  function formatPercentage(value) {
    if (!(value > 0)) return "0";
    if (value < 1) return value < 0.05 ? "<0.1" : value.toFixed(1);
    return String(Math.floor(value + 0.5));
  }

  function journeyPageSelects() {
    return [...(journeyPages?.querySelectorAll("select[name='journey_page']") || [])];
  }

  function refreshJourneyRows() {
    if (!journeyPages) return;
    const rows = [...journeyPages.querySelectorAll(".analytics-journey-page-row")];
    rows.forEach((row, index) => {
      const select = row.querySelector("select[name='journey_page']");
      const label = row.querySelector("label");
      const remove = row.querySelector(".analytics-remove-journey-page");
      const number = index + 1;
      if (select) {
        select.id = `journey-page-${number}`;
        select.setAttribute("aria-label", `Page ${number} in ordered path`);
      }
      if (label) {
        label.htmlFor = `journey-page-${number}`;
        label.textContent = `Page ${number} in ordered path`;
      }
      if (remove) remove.setAttribute("aria-label", `Remove page ${number}`);
    });
    if (addJourneyPage) addJourneyPage.disabled = rows.length >= Number(journeyPages.dataset.maxPages || 8);
  }

  function addJourneyPathPage(value = "") {
    if (!journeyPages || !journeyTemplate) return null;
    if (journeyPageSelects().length >= Number(journeyPages.dataset.maxPages || 8)) return null;
    const row = journeyTemplate.content.firstElementChild.cloneNode(true);
    const select = row.querySelector("select[name='journey_page']");
    if (select) select.value = value;
    journeyPages.appendChild(row);
    refreshJourneyRows();
    return select;
  }

  addJourneyPage?.addEventListener("click", () => {
    addJourneyPathPage()?.focus();
  });

  journeyPages?.addEventListener("click", (event) => {
    const removeButton = event.target.closest(".analytics-remove-journey-page");
    if (!removeButton) return;
    removeButton.closest(".analytics-journey-page-row")?.remove();
    refreshJourneyRows();
  });
  refreshJourneyRows();

  const chartHost = document.getElementById("analytics-sankey");
  const chartPayload = document.getElementById("analytics-sankey-data");
  if (!chartHost || !chartPayload) return;

  let edges;
  try {
    edges = JSON.parse(chartPayload.textContent || "[]");
  } catch (_) {
    edges = [];
  }
  if (!Array.isArray(edges) || !edges.length) return;

  const svgNS = "http://www.w3.org/2000/svg";
  const maxStage = Math.max(...edges.map((edge) => Number(edge.step) || 1));
  const stageGap = 205;
  const margin = { top: 52, bottom: 22, left: 100 };
  const nodeWidth = 14;
  const palette = ["#d7c07a", "#83c9bd", "#b4a1d4", "#d8a875", "#82a9d4"];
  const nodesByKey = new Map();

  function nodeFor(stage, label) {
    const key = `${stage}:${label}`;
    if (!nodesByKey.has(key)) {
      nodesByKey.set(key, {
        key,
        stage,
        label: String(label),
        incoming: [],
        outgoing: [],
      });
    }
    return nodesByKey.get(key);
  }

  const links = edges.map((edge) => {
    const step = Math.max(1, Number(edge.step) || 1);
    const source = nodeFor(step - 1, edge.source);
    const target = nodeFor(step, edge.target);
    const link = {
      source,
      target,
      count: Math.max(0, Number(edge.count) || 0),
      previousStepCount: Math.max(0, Number(edge.previous_step_count) || 0),
      step,
      isMorePages: Boolean(edge.is_more_pages),
    };
    source.outgoing.push(link);
    target.incoming.push(link);
    return link;
  });

  const columns = Array.from({ length: maxStage + 1 }, (_, stage) =>
    [...nodesByKey.values()]
      .filter((node) => node.stage === stage)
      .sort((a, b) => {
        const aWeight = Math.max(
          a.incoming.reduce((sum, link) => sum + link.count, 0),
          a.outgoing.reduce((sum, link) => sum + link.count, 0),
        );
        const bWeight = Math.max(
          b.incoming.reduce((sum, link) => sum + link.count, 0),
          b.outgoing.reduce((sum, link) => sum + link.count, 0),
        );
        return bWeight - aWeight || a.label.localeCompare(b.label);
      }),
  );
  const maxLinksInColumn = Math.max(...columns.map((column) => column.length), 1);
  const height = Math.max(320, margin.top + margin.bottom + maxLinksInColumn * 50);
  const width = margin.left + maxStage * stageGap + nodeWidth + 235;
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "presentation");
  svg.setAttribute("focusable", "false");

  columns.forEach((column, stage) => {
    const gap = 14;
    const nodeHeight = 30;
    const totalHeight = column.length * nodeHeight + Math.max(0, column.length - 1) * gap;
    let y = margin.top + Math.max(0, (height - margin.top - margin.bottom - totalHeight) / 2);
    column.forEach((node) => {
      node.x = margin.left + stage * stageGap;
      node.y = y;
      node.height = nodeHeight;
      node.outOffset = 0;
      node.inOffset = 0;
      y += nodeHeight + gap;
    });
  });

  const maxCount = Math.max(...links.map((link) => link.count), 1);
  links.forEach((link) => {
    link.width = Math.max(1.5, Math.min(20, 3 + 17 * Math.sqrt(link.count / maxCount)));
  });

  function selectedJourneyPages() {
    return journeyPageSelects().map((select) => select.value).filter(Boolean);
  }

  function mostCommonJourneyTo(link) {
    const path = Array(link.step);
    path[link.step - 1] = link.source.label;
    let current = link.source.label;
    for (let step = link.step - 1; step >= 1; step -= 1) {
      const parent = edges
        .filter((edge) => Number(edge.step) === step && edge.target === current &&
          edge.target !== "More pages" && edge.target !== "Exit")
        .sort((a, b) => Number(b.count) - Number(a.count))[0];
      if (!parent) return null;
      path[step - 1] = parent.source;
      current = parent.source;
    }
    return path;
  }

  function applyLinkAsJourney(link) {
    if (link.isMorePages || link.target.label === "More pages") {
      const currentDepth = Number(journeyDepth?.value || 5);
      const maxDepth = Number(chartHost.dataset.maxDepth || 20);
      if (currentDepth >= maxDepth) {
        if (journeyStatus) journeyStatus.textContent = `The path view is already showing the maximum ${maxDepth} pages.`;
        return;
      }
      if (journeyDepth) journeyDepth.value = String(Math.min(maxDepth, currentDepth + 5));
      journeyForm?.requestSubmit();
      return;
    }

    if (link.target.label === "Exit") {
      if (journeyStatus) journeyStatus.textContent = "Exit bands show sessions leaving after this page. Choose page bands to filter an ordered page sequence.";
      return;
    }

    const selected = selectedJourneyPages();
    let prefix = null;
    if (selected.length >= link.step && selected[link.step - 1] === link.source.label) {
      prefix = selected.slice(0, link.step);
    } else if (link.step === 1) {
      prefix = [link.source.label];
    } else {
      prefix = mostCommonJourneyTo(link);
    }

    if (!prefix) {
      if (journeyStatus) journeyStatus.textContent = "Select an earlier page band first to build this path.";
      return;
    }
    const nextPath = [...prefix, link.target.label];
    while (journeyPageSelects().length > nextPath.length) {
      journeyPages.lastElementChild.remove();
    }
    while (journeyPageSelects().length < nextPath.length) addJourneyPathPage();
    journeyPageSelects().forEach((select, index) => { select.value = nextPath[index] || ""; });
    journeyForm?.requestSubmit();
  }

  links.forEach((link) => {
    const sourceTotal = link.source.outgoing.reduce((sum, item) => sum + item.width, 0);
    const targetTotal = link.target.incoming.reduce((sum, item) => sum + item.width, 0);
    const sourceY = link.source.y + (link.source.height - sourceTotal) / 2 + link.source.outOffset + link.width / 2;
    const targetY = link.target.y + (link.target.height - targetTotal) / 2 + link.target.inOffset + link.width / 2;
    link.source.outOffset += link.width;
    link.target.inOffset += link.width;
    const startX = link.source.x + nodeWidth;
    const endX = link.target.x;
    const curve = Math.max(32, (endX - startX) * 0.48);
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", `M ${startX} ${sourceY} C ${startX + curve} ${sourceY}, ${endX - curve} ${targetY}, ${endX} ${targetY}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", palette[(link.step - 1) % palette.length]);
    path.setAttribute("stroke-width", String(link.width));
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-opacity", "0.42");
    path.classList.add("sankey-link");
    path.setAttribute("role", "button");
    path.setAttribute("tabindex", "0");
    const previousCount = link.previousStepCount;
    const share = formatPercentage(previousCount ? link.count * 100 / previousCount : 0);
    const action = link.isMorePages ? "Click to show the next pages." : "Click to filter this ordered path.";
    const description = `${link.source.label} → ${link.target.label}: ${link.count.toLocaleString()} sessions, ${share}% of the previous step (${previousCount.toLocaleString()} sessions). ${action}`;
    path.setAttribute("aria-label", description);
    const title = document.createElementNS(svgNS, "title");
    title.textContent = description;
    path.appendChild(title);
    path.addEventListener("click", () => applyLinkAsJourney(link));
    path.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        applyLinkAsJourney(link);
      }
    });
    svg.appendChild(path);
  });

  columns.forEach((column, stage) => {
    const x = margin.left + stage * stageGap;
    const heading = document.createElementNS(svgNS, "text");
    heading.setAttribute("x", String(x + nodeWidth / 2));
    heading.setAttribute("y", "28");
    heading.setAttribute("text-anchor", "middle");
    heading.setAttribute("class", "sankey-stage-label");
    heading.textContent = stage === 0 ? "Entry" : `Page ${stage + 1}`;
    svg.appendChild(heading);

    column.forEach((node) => {
      const rect = document.createElementNS(svgNS, "rect");
      rect.setAttribute("x", String(node.x));
      rect.setAttribute("y", String(node.y));
      rect.setAttribute("width", String(nodeWidth));
      rect.setAttribute("height", String(Math.max(16, node.height)));
      rect.setAttribute("rx", "5");
      rect.setAttribute("fill", node.label === "Exit" ? "#77746b" : palette[stage % palette.length]);
      rect.setAttribute("fill-opacity", "0.9");
      const nodeTitle = document.createElementNS(svgNS, "title");
      nodeTitle.textContent = node.label;
      rect.appendChild(nodeTitle);
      svg.appendChild(rect);

      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", String(node.x + nodeWidth + 9));
      label.setAttribute("y", String(node.y + node.height / 2 + 4));
      label.setAttribute("class", "sankey-node-label");
      const fullLabel = node.label;
      label.textContent = fullLabel.length > 23 ? `${fullLabel.slice(0, 20)}…` : fullLabel;
      const labelTitle = document.createElementNS(svgNS, "title");
      labelTitle.textContent = fullLabel;
      label.appendChild(labelTitle);
      svg.appendChild(label);
    });
  });

  chartHost.replaceChildren(svg);
})();
