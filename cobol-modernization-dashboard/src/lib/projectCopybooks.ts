/** Client-side COPY expansion using in-memory project files (ZIP contents). */

function normalizePathMap(files: Map<string, string>): Map<string, string> {
  const out = new Map<string, string>();
  for (const [path, content] of files) {
    const base = path.split("/").pop() ?? path;
    out.set(base.toUpperCase(), content);
    out.set(base, content);
    out.set(path.replace(/\\/g, "/").toUpperCase(), content);
  }
  return out;
}

function resolveCopyText(name: string, map: Map<string, string>, stack: Set<string>): string {
  const keys = [`${name.toUpperCase()}.CPY`, `${name}.cpy`, `${name.toUpperCase()}`, name];
  let body: string | undefined;
  for (const k of keys) {
    const hit = map.get(k) ?? map.get(k.toUpperCase());
    if (hit !== undefined) {
      body = hit;
      break;
    }
  }
  if (body === undefined) {
    return `      *> COPY ${name} (unresolved — file not in project ZIP)\n`;
  }
  const sig = name.toUpperCase();
  if (stack.has(sig)) {
    return `      *> COPY ${name} (circular)\n`;
  }
  stack.add(sig);
  try {
    return expandCopybooksInSource(body, map, stack);
  } finally {
    stack.delete(sig);
  }
}

function expandCopybooksInSource(source: string, rawMap: Map<string, string>, stack: Set<string>): string {
  const map = normalizePathMap(rawMap);
  const copyRe =
    /^(\s*)COPY\s+([A-Z0-9-]+)(\s+REPLACING[\s\S]*?)?\s*\.?\s*$/gim;
  return source.replace(copyRe, (_full, indent: string, name: string) => {
    const expanded = resolveCopyText(String(name), map, stack);
    const padded = expanded
      .split(/\r?\n/)
      .map((line, i) => (i === 0 ? `${indent}${line}` : `${indent}${line}`))
      .join("\n");
    return padded;
  });
}

export function expandCopybooks(source: string, files: Map<string, string>): string {
  return expandCopybooksInSource(source, files, new Set());
}

/** Sort .cbl entries for batch runs: dependency heuristic, then name. Preserves input object identity (path, etc.). */
export function topologicalCobolOrder<T extends { filename: string; sourceCode: string }>(entries: T[]): T[] {
  const byName = new Map(
    entries.map((f) => [f.filename.toUpperCase().replace(/\.(CBL|COB)\s*$/i, ""), f] as const),
  );
  const copyDep = (src: string) => {
    const deps = new Set<string>();
    const re = /^\s*COPY\s+([A-Z0-9-]+)/gim;
    let m: RegExpExecArray | null;
    while ((m = re.exec(src))) {
      deps.add(m[1].toUpperCase());
    }
    return deps;
  };

  const nodes = [...entries];
  const referenced = new Set<string>();
  for (const n of nodes) {
    for (const d of copyDep(n.sourceCode)) {
      if (byName.has(d)) referenced.add(byName.get(d)!.filename.toUpperCase());
    }
  }

  // Files that are never referenced as a copybook name come first (heuristic), then alphabetical.
  const isReferenced = (fn: string) => referenced.has(fn.toUpperCase());
  return [...nodes].sort((a, b) => {
    const ar = isReferenced(a.filename) ? 1 : 0;
    const br = isReferenced(b.filename) ? 1 : 0;
    if (ar !== br) return ar - br;
    return a.filename.localeCompare(b.filename);
  });
}
