(() => {
  const rangeMode = document.getElementById("analytics-range-mode");
  const rangeFields = document.querySelectorAll("[data-range-fields]");
  const periodCount = document.getElementById("analytics-period-count");
  const periodUnit = document.querySelector("[name='unit']");

  function updateRangeFields() {
    const mode = rangeMode?.value || "rolling";
    rangeFields.forEach((field) => {
      const active = field.dataset.rangeFields === mode;
      field.hidden = !active;
      if (field instanceof HTMLFieldSetElement) field.disabled = !active;
      field.querySelectorAll("input, select").forEach((control) => {
        control.disabled = !active;
      });
    });
    if (periodCount && periodUnit) {
      periodCount.max = ({ days: "365", weeks: "104", months: "60" })[periodUnit.value] || "365";
    }
  }

  rangeMode?.addEventListener("change", updateRangeFields);
  periodUnit?.addEventListener("change", updateRangeFields);
  updateRangeFields();

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
    const link = { source, target, count: Math.max(0, Number(edge.count) || 0), step };
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
    const title = document.createElementNS(svgNS, "title");
    title.textContent = `${link.source.label} → ${link.target.label}: ${link.count.toLocaleString()} sessions`;
    path.appendChild(title);
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
