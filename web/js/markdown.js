// Turns a model's answer (Markdown) into HTML for the page: paragraphs, lists, headings, tables, `code`, **bold**,
// and ``` blocks as code windows with a Copy button. Everything is escaped first, so an answer can't put its own
// HTML on the page. Works on half-written answers too: an unfinished ``` block shows as a code window as it grows.

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function inline(s) {
  return escape(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
}

// A diff: added lines green, removed red, so a change is easy to read.
function diffLines(code) {
  return code.replace(/\n$/, "").split("\n").map((line) => {
    const kind = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : line.startsWith("@@") ? "hunk" : "";
    return kind ? `<span class="diff-${kind}">${escape(line)}</span>` : escape(line);
  }).join("\n");
}

function codeWindow(language, code) {
  const name = language.trim() || "code";
  return `<div class="code"><div class="code-head"><span>${escape(name)}</span>` +
    `<button type="button" class="button copy-code">Copy</button></div>` +
    `<pre><code>${name === "diff" ? diffLines(code) : escape(code.replace(/\n$/, ""))}</code></pre></div>`;
}

const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

function blocks(text) {
  const out = [];
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 2, 4); // # → h3, ## and more → h4
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      i++;
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|?[\s:-]+\|[\s|:-]*$/.test(lines[i + 1] || "")) {
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push(`<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead>` +
        `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    const bullet = /^\s*[-*+]\s+/;
    const number = /^\s*\d+[.)]\s+/;
    if (bullet.test(line) || number.test(line)) {
      const kind = bullet.test(line) ? bullet : number;
      const items = [];
      while (i < lines.length && (kind.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (kind.test(lines[i])) items.push(lines[i].replace(kind, ""));
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      const tag = kind === bullet ? "ul" : "ol";
      out.push(`<${tag}>${items.map((it) => `<li>${inline(it)}</li>`).join("")}</${tag}>`);
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*[-*+]\s|\s*\d+[.)]\s|\s*\|)/.test(lines[i])) para.push(lines[i++]);
    if (!para.length) para.push(lines[i++]);
    out.push(`<p>${para.map(inline).join("<br>")}</p>`);
  }
  return out.join("");
}

export function render(text) {
  let html = "";
  let at = 0;
  const fence = /```([^\n`]*)\n([\s\S]*?)(?:```|$)/g;
  for (const match of text.matchAll(fence)) {
    html += blocks(text.slice(at, match.index));
    html += codeWindow(match[1], match[2]);
    at = match.index + match[0].length;
  }
  return html + blocks(text.slice(at));
}

// One listener for every Copy button on the page.
document.addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-code");
  if (!button) return;
  const code = button.closest(".code").querySelector("code").textContent;
  try {
    await navigator.clipboard.writeText(code);
    button.textContent = "Copied";
  } catch {
    // http:// from a phone isn't allowed to use the clipboard: select the code so it can be copied by hand
    const range = document.createRange();
    range.selectNodeContents(button.closest(".code").querySelector("code"));
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    button.textContent = "Selected";
  }
  setTimeout(() => (button.textContent = "Copy"), 1500);
});
