export function renderMarkdown(text: string | undefined) {
  const lines = normalizeMarkdownDocument(text).replace(/\r\n?/g, '\n').split('\n');
  const html: string[] = [];
  let paragraph: string[] = [];
  let codeFence: { language: string } | null = null;
  let codeLines: string[] = [];

  function flushParagraph() {
    if (!paragraph.length) return;
    html.push(`<p>${inlineMarkdown(paragraph.join(' '))}</p>`);
    paragraph = [];
  }

  function flushCode() {
    if (!codeFence) return;
    const language = codeFence.language ? ` data-language="${escapeHtml(codeFence.language)}"` : '';
    html.push(`<pre${language}><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
    codeFence = null;
    codeLines = [];
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    const fenceMatch = trimmed.match(/^```([A-Za-z0-9_-]+)?\s*$/);

    if (codeFence) {
      if (fenceMatch) {
        flushCode();
      } else {
        codeLines.push(line);
      }
      continue;
    }

    if (fenceMatch) {
      flushParagraph();
      codeFence = { language: fenceMatch[1] || '' };
      codeLines = [];
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      html.push('<hr>');
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[1].length, 6);
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    if (isTableStart(lines, index)) {
      flushParagraph();
      const table = collectTable(lines, index);
      html.push(renderMarkdownTable(table.rows));
      index = table.nextIndex - 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      flushParagraph();
      const list = collectList(lines, index, 'ul');
      html.push(renderMarkdownList(list.items, 'ul'));
      index = list.nextIndex - 1;
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      flushParagraph();
      const list = collectList(lines, index, 'ol');
      html.push(renderMarkdownList(list.items, 'ol'));
      index = list.nextIndex - 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      flushParagraph();
      const quote = collectBlockquote(lines, index);
      html.push(`<blockquote>${renderMarkdown(quote.lines.join('\n'))}</blockquote>`);
      index = quote.nextIndex - 1;
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  flushCode();
  return html.join('');
}

function normalizeMarkdownDocument(text: string | undefined) {
  const source = String(text || '').trim();
  const fenced = source.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i);
  return fenced ? fenced[1].trim() : source;
}

function isTableStart(lines: string[], index: number) {
  const current = lines[index] || '';
  const next = lines[index + 1] || '';
  return current.includes('|') && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(next);
}

function collectTable(lines: string[], index: number) {
  const rows = [splitTableRow(lines[index])];
  index += 2;
  while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
    rows.push(splitTableRow(lines[index]));
    index += 1;
  }
  return { rows, nextIndex: index };
}

function splitTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function renderMarkdownTable(rows: string[][]) {
  const header = rows[0] || [];
  const body = rows.slice(1);
  return `
    <div class="markdown-table-scroll">
      <table>
        <thead><tr>${header.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join('')}</tr></thead>
        <tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join('')}</tr>`).join('')}</tbody>
      </table>
    </div>
  `;
}

function collectList(lines: string[], index: number, type: 'ul' | 'ol') {
  const pattern = type === 'ol' ? /^\s*\d+\.\s+(.+)$/ : /^\s*[-*]\s+(.+)$/;
  const items: string[] = [];
  while (index < lines.length) {
    const match = lines[index].match(pattern);
    if (!match) break;
    items.push(match[1]);
    index += 1;
  }
  return { items, nextIndex: index };
}

function renderMarkdownList(items: string[], type: 'ul' | 'ol') {
  return `<${type}>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join('')}</${type}>`;
}

function collectBlockquote(lines: string[], index: number) {
  const quoteLines: string[] = [];
  while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
    quoteLines.push(lines[index].replace(/^\s*>\s?/, ''));
    index += 1;
  }
  return { lines: quoteLines, nextIndex: index };
}

function inlineMarkdown(text: string) {
  return String(text)
    .split(/(`[^`]+`)/g)
    .map((part) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
      }
      return inlineText(part);
    })
    .join('');
}

function inlineText(text: string) {
  const source = String(text);
  const html: string[] = [];
  const linkPattern = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = linkPattern.exec(source)) !== null) {
    html.push(inlineDecorations(source.slice(cursor, match.index)));
    html.push(`<a href="${escapeHtml(match[2])}" target="_blank" rel="noreferrer">${inlineDecorations(match[1])}</a>`);
    cursor = match.index + match[0].length;
  }

  html.push(inlineDecorations(source.slice(cursor)));
  return html.join('');
}

function inlineDecorations(text: string) {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+)__/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
    .replace(/(^|[^_])_([^_]+)_/g, '$1<em>$2</em>');
}

function escapeHtml(value: string) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
