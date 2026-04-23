# Codex Prompt — Frontend Overhaul (React/Next.js)
**Stack:** React 18 · TypeScript · Tailwind CSS · shadcn/ui
**No mock data — all API calls are real**

---

## SYSTEM PROMPT

You are a senior frontend engineer. Implement a complete UI overhaul for a
COBOL-to-Java modernization platform. The UI has 4 main pages and a shared
sidebar. Every feature must make real API calls — no mock data, no hardcoded
responses.

---

## DESIGN SYSTEM

### Color Palette (Tailwind classes)

```
Background base:     bg-gray-950
Surface cards:       bg-gray-900   border border-gray-800
Surface elevated:    bg-gray-850   (custom: #1a1f2e)
Accent primary:      text-violet-400  bg-violet-600
Accent success:      text-emerald-400 bg-emerald-600/20
Accent warning:      text-amber-400   bg-amber-600/20
Accent error:        text-red-400     bg-red-600/20
Text primary:        text-gray-100
Text secondary:      text-gray-400
Border:              border-gray-700
```

### Pipeline Stage Color Coding
Each stage has a distinct color for badges and diff highlighting:

| Stage | Color class |
|---|---|
| Parser output | text-sky-400 bg-sky-900/30 border-sky-700 |
| JCL manifest | text-orange-400 bg-orange-900/30 border-orange-700 |
| COPY resolver | text-pink-400 bg-pink-900/30 border-pink-700 |
| Analysis output | text-violet-400 bg-violet-900/30 border-violet-700 |
| Converted Java | text-emerald-400 bg-emerald-900/30 border-emerald-700 |
| Test results | text-amber-400 bg-amber-900/30 border-amber-700 |

---

## PAGE 1 — SINGLE FILE CONVERSION (`/`)

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│  SIDEBAR (left, fixed 240px)                                  │
│  • Single File    ← active                                    │
│  • Project Upload                                             │
│  • Testing Agent                                              │
│  • Settings                                                   │
├──────────────────────────────────────────────────────────────┤
│  HEADER: "COBOL Modernizer"  [Pipeline Mode dropdown]        │
├────────────────────┬─────────────────────────────────────────┤
│  INPUT PANEL       │  OUTPUT PANEL                           │
│  (Monaco editor)   │  (Monaco editor read-only)              │
│  .cbl / .cob drop  │  [sky badge] Parser  [violet] Analysis  │
│                    │  [emerald] Java  [amber] Tests           │
│  [RUN PIPELINE]    │                                         │
│                    │  Output tab content                     │
└────────────────────┴─────────────────────────────────────────┘
```

### Pipeline Mode Selector Component

```tsx
type PipelineMode =
  | "full"           // Parse → Analyse → Convert → Test
  | "parse_only"     // Parse only
  | "parse_analyse"  // Parse + Analyse
  | "analyse_only"   // Analyse only (requires pre-parsed)
  | "no_parse";      // Raw COBOL → Java (no parse/analyse)

const MODES: { value: PipelineMode; label: string; description: string; color: string }[] = [
  { value: "full",          label: "Full Pipeline",         color: "violet",
    description: "Parse → Analyse → Segment → Convert → Test" },
  { value: "parse_only",    label: "Parse Only",            color: "sky",
    description: "Extract symbol table and call graph only" },
  { value: "parse_analyse", label: "Parse + Analyse",       color: "pink",
    description: "Parse then extract business rules" },
  { value: "analyse_only",  label: "Analyse Only",          color: "violet",
    description: "Analysis using pre-computed parser output" },
  { value: "no_parse",      label: "Direct Convert",        color: "emerald",
    description: "COBOL → Java without parse/analyse pass" },
];

export function PipelineModeSelector({ value, onChange }) {
  return (
    <div className="flex flex-col gap-1 p-2 bg-gray-900 border border-gray-700 rounded-lg">
      <span className="text-xs text-gray-400 px-2 pb-1 uppercase tracking-wider">
        Pipeline Mode
      </span>
      {MODES.map(mode => (
        <button
          key={mode.value}
          onClick={() => onChange(mode.value)}
          className={`
            flex items-start gap-3 px-3 py-2 rounded-md text-left transition-all
            ${value === mode.value
              ? `bg-${mode.color}-900/40 border border-${mode.color}-700 text-${mode.color}-300`
              : "hover:bg-gray-800 text-gray-400"
            }
          `}
        >
          <div>
            <div className="text-sm font-medium">{mode.label}</div>
            <div className="text-xs opacity-70 mt-0.5">{mode.description}</div>
          </div>
        </button>
      ))}
    </div>
  );
}
```

### Output Tabs with Stage Badges

```tsx
const OUTPUT_TABS = [
  { id: "parser",   label: "Parser Output",  colorClass: "sky",    icon: "🔍" },
  { id: "analysis", label: "Analysis",        colorClass: "violet", icon: "🧠" },
  { id: "java",     label: "Java Output",     colorClass: "emerald",icon: "☕" },
  { id: "tests",    label: "Test Report",     colorClass: "amber",  icon: "🧪" },
];

// Each tab renders its content with the stage's accent color border
// The Java tab has a [⬇ Download .java] button
// The Test Report tab shows the TestDashboard component
```

### API Call

```tsx
async function runPipeline(source: string, mode: PipelineMode) {
  const res = await fetch("/api/pipeline/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cobol_source: source, mode })
  });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}
```

---

## PAGE 2 — PROJECT UPLOAD (`/project`)

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  [Upload ZIP] button  →  drag-drop zone                     │
├─────────────────────────────────────────────────────────────┤
│  LEFT: FILE EXPLORER (IDE-style)  │  RIGHT: FILE VIEWER     │
│                                   │  (Monaco, read-only)    │
│  📁 project-root/                 │                         │
│    📁 copybooks/                  │  Selected file content  │
│      📄 INVDATA.cpy (pink)        │  with syntax highlight  │
│    📁 jcl/                        │                         │
│      📄 INVJOB.jcl (orange)       │                         │
│    📄 INVMGMT.cbl (sky)           │                         │
│    📄 INVRPT.cbl  (sky)           │                         │
├───────────────────────────────────┴─────────────────────────┤
│  PIPELINE CONTROLS                                           │
│  Mode: [Full Pipeline ▼]  [▶ Run All Files]                 │
├─────────────────────────────────────────────────────────────┤
│  RESULTS TABLE                                               │
│  File | Status | Parser | Analysis | Java | Tests | Download│
│  INVMGMT.cbl | ✅ | ✅ sky | ✅ violet | ✅ emerald | 3❌ amber | ⬇|
└─────────────────────────────────────────────────────────────┘
```

### File Explorer Component (IDE-style)

```tsx
interface ProjectFile {
  path: string;
  type: "cobol" | "jcl" | "copybook" | "other";
  size: number;
  content: string;
}

const FILE_TYPE_STYLE = {
  cobol:     { color: "text-sky-400",    icon: "📄", badge: "bg-sky-900/40 text-sky-300" },
  jcl:       { color: "text-orange-400", icon: "⚙️", badge: "bg-orange-900/40 text-orange-300" },
  copybook:  { color: "text-pink-400",   icon: "📋", badge: "bg-pink-900/40 text-pink-300" },
  other:     { color: "text-gray-400",   icon: "📄", badge: "bg-gray-800 text-gray-400" },
};

export function FileExplorer({
  files,
  selectedFile,
  onSelect
}: {
  files: ProjectFile[];
  selectedFile: ProjectFile | null;
  onSelect: (f: ProjectFile) => void;
}) {
  // Build folder tree from flat file paths
  const tree = buildFolderTree(files);

  return (
    <div className="h-full overflow-y-auto bg-gray-900 border-r border-gray-700 font-mono text-sm">
      <div className="px-3 py-2 text-xs text-gray-500 uppercase tracking-wider">
        Project Explorer
      </div>
      <FileTree
        node={tree}
        depth={0}
        selectedPath={selectedFile?.path}
        onSelect={onSelect}
        typeStyle={FILE_TYPE_STYLE}
      />
    </div>
  );
}

// buildFolderTree converts flat paths to nested tree structure
function buildFolderTree(files: ProjectFile[]) {
  const root: any = { name: "/", children: {}, file: null };
  for (const f of files) {
    const parts = f.path.replace(/^\//, "").split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!node.children[parts[i]]) {
        node.children[parts[i]] = { name: parts[i], children: {}, file: null };
      }
      node = node.children[parts[i]];
    }
    const fname = parts[parts.length - 1];
    node.children[fname] = { name: fname, children: {}, file: f };
  }
  return root;
}
```

### Results Table

```tsx
export function ProjectResultsTable({ results }: { results: ConversionResult[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-700 text-gray-400">
            <th className="text-left px-4 py-3">File</th>
            <th className="px-3 py-3">Status</th>
            <th className="px-3 py-3 text-sky-400">Parser</th>
            <th className="px-3 py-3 text-violet-400">Analysis</th>
            <th className="px-3 py-3 text-emerald-400">Java</th>
            <th className="px-3 py-3 text-amber-400">Tests</th>
            <th className="px-3 py-3">Download</th>
          </tr>
        </thead>
        <tbody>
          {results.map(r => (
            <ResultRow key={r.file} result={r} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultRow({ result }: { result: ConversionResult }) {
  const tests = result.test_report?.summary;
  const testColor = tests
    ? tests.critical_failures > 0 ? "text-red-400"
    : tests.high_failures > 0     ? "text-amber-400"
    : "text-emerald-400"
    : "text-gray-500";

  return (
    <tr className="border-b border-gray-800 hover:bg-gray-850 transition-colors">
      <td className="px-4 py-3 text-sky-300 font-mono">{result.file}</td>
      <td className="px-3 py-3 text-center">
        {result.errors?.length ? "❌" : "✅"}
      </td>
      <td className="px-3 py-3 text-center">
        <StageStatusBadge present={!!result.parser_output} color="sky" />
      </td>
      <td className="px-3 py-3 text-center">
        <StageStatusBadge present={!!result.analysis_output} color="violet" />
      </td>
      <td className="px-3 py-3 text-center">
        <StageStatusBadge present={!!result.java_source} color="emerald" />
      </td>
      <td className={`px-3 py-3 text-center font-mono ${testColor}`}>
        {tests ? `${tests.passed}/${tests.total}` : "—"}
      </td>
      <td className="px-3 py-3 text-center">
        {result.java_source && (
          <DownloadButton javaSource={result.java_source} file={result.file} />
        )}
      </td>
    </tr>
  );
}
```

### Download Buttons

```tsx
function DownloadButton({ javaSource, file }: { javaSource: string; file: string }) {
  const download = async () => {
    const res = await fetch("/api/download/java", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        java_source: javaSource,
        class_name: Path.basename(file, ".cbl")
      })
    });
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = file.replace(".cbl", ".java");
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <button
      onClick={download}
      className="px-2 py-1 text-xs bg-emerald-900/40 text-emerald-300
                 border border-emerald-700 rounded hover:bg-emerald-800 transition-colors"
    >
      ⬇ .java
    </button>
  );
}

// Download all as ZIP
function DownloadAllButton({ results }: { results: ConversionResult[] }) {
  const download = async () => {
    const res = await fetch("/api/download/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ results })
    });
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = "converted_project.zip";
    a.click();
  };
  return (
    <button
      onClick={download}
      className="px-4 py-2 bg-violet-700 hover:bg-violet-600 text-white
                 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
    >
      ⬇ Download All (.zip)
    </button>
  );
}
```

---

## PAGE 3 — TESTING AGENT (`/testing`)

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER: "Testing Agent"                                         │
│  [▶ Run Tests] button                                           │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  PARSER      │  JCL         │  CONVERSION  │  BEHAVIORAL        │
│  sky-themed  │  orange-themed│  emerald     │  amber-themed      │
│  card        │  card        │  card        │  card              │
│  ✅ 12/12    │  ✅ 4/4     │  ❌ 2/5      │  ✅ 4/5            │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│  PIPELINE STATUS BAR                                             │
│  ● PARSER  ──→  ● JCL  ──→  ● CONVERSION  ──→  ● BEHAVIORAL    │
│  (colored by pass/fail)                                          │
├─────────────────────────────────────────────────────────────────┤
│  TEST DETAIL TABLE (expandable rows)                             │
│  # | ID | Description | Result | Severity | Detail              │
│  1 | NO_DO_WHILE | No do-while loops | ❌ FAIL | high | ...     │
└─────────────────────────────────────────────────────────────────┘
```

### Test Summary Cards

```tsx
const SUITE_CONFIG = {
  parser_tests:     { label: "Parser",     color: "sky",     icon: "🔍" },
  conversion_tests: { label: "Conversion", color: "emerald", icon: "☕" },
  behavioral_tests: { label: "Behavioral", color: "amber",   icon: "🏃" },
};

export function TestSuiteCard({
  label, color, icon, tests
}: {
  label: string; color: string; icon: string; tests: TestResult[]
}) {
  const passed = tests.filter(t => t.passed).length;
  const total  = tests.length;
  const allPass = passed === total;

  return (
    <div className={`
      rounded-xl border p-4
      ${allPass
        ? `bg-${color}-900/20 border-${color}-700`
        : "bg-red-900/20 border-red-700"}
    `}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className={`font-semibold text-${color}-300`}>{label}</span>
        </div>
        <span className={`
          text-2xl font-bold font-mono
          ${allPass ? `text-${color}-400` : "text-red-400"}
        `}>
          {passed}/{total}
        </span>
      </div>
      <div className="w-full bg-gray-800 rounded-full h-1.5">
        <div
          className={`h-1.5 rounded-full bg-${color}-500 transition-all`}
          style={{ width: `${total > 0 ? (passed/total)*100 : 0}%` }}
        />
      </div>
      {!allPass && (
        <div className="mt-2 text-xs text-red-400">
          {total - passed} failure{total - passed > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
```

### Pipeline Status Bar

```tsx
export function PipelineStatusBar({ report }: { report: TestReport }) {
  const stages = [
    { key: "parser_tests",     label: "Parser",     color: "sky" },
    { key: "conversion_tests", label: "Conversion", color: "emerald" },
    { key: "behavioral_tests", label: "Behavioral", color: "amber" },
  ];

  return (
    <div className="flex items-center gap-0 p-4 bg-gray-900 rounded-xl border border-gray-700">
      {stages.map((stage, i) => {
        const tests  = report[stage.key as keyof TestReport] as TestResult[];
        const allPass = tests?.every(t => t.passed);
        return (
          <React.Fragment key={stage.key}>
            <div className="flex flex-col items-center gap-1">
              <div className={`
                w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
                ${allPass
                  ? `bg-${stage.color}-600 text-white`
                  : "bg-red-600 text-white"}
              `}>
                {allPass ? "✓" : "✗"}
              </div>
              <span className={`text-xs text-${stage.color}-400`}>{stage.label}</span>
            </div>
            {i < stages.length - 1 && (
              <div className={`
                flex-1 h-0.5 mx-2 mt-[-12px]
                ${allPass ? `bg-${stage.color}-600` : "bg-red-700"}
              `} />
            )}
          </React.Fragment>
        );
      })}
      <div className={`
        ml-4 px-3 py-1 rounded-full text-xs font-bold
        ${report.is_pipeline_green
          ? "bg-emerald-600 text-white"
          : "bg-red-600 text-white"}
      `}>
        {report.is_pipeline_green ? "✅ GREEN" : "🔴 FAILING"}
      </div>
    </div>
  );
}
```

### Test Detail Table with Expandable Rows

```tsx
export function TestDetailTable({ tests }: { tests: TestResult[] }) {
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  const severityColor = {
    critical: "text-red-400",
    high:     "text-amber-400",
    medium:   "text-yellow-400",
    low:      "text-gray-400"
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-700">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-700 bg-gray-900">
            <th className="px-4 py-3 text-left text-gray-400">#</th>
            <th className="px-4 py-3 text-left text-gray-400">ID</th>
            <th className="px-4 py-3 text-left text-gray-400">Description</th>
            <th className="px-4 py-3 text-center text-gray-400">Result</th>
            <th className="px-4 py-3 text-center text-gray-400">Severity</th>
          </tr>
        </thead>
        <tbody>
          {tests.map((test, i) => (
            <React.Fragment key={test.id}>
              <tr
                className={`
                  border-b border-gray-800 cursor-pointer transition-colors
                  ${test.passed ? "hover:bg-gray-850" : "bg-red-950/20 hover:bg-red-950/40"}
                `}
                onClick={() => {
                  const next = new Set(expanded);
                  next.has(test.id) ? next.delete(test.id) : next.add(test.id);
                  setExpanded(next);
                }}
              >
                <td className="px-4 py-3 text-gray-500 font-mono">{i+1}</td>
                <td className="px-4 py-3 text-gray-300 font-mono text-xs">{test.id}</td>
                <td className="px-4 py-3 text-gray-300">{test.description}</td>
                <td className="px-4 py-3 text-center">
                  {test.passed ? "✅" : "❌"}
                </td>
                <td className={`px-4 py-3 text-center text-xs uppercase font-bold
                  ${severityColor[test.severity as keyof typeof severityColor]}`}>
                  {test.severity}
                </td>
              </tr>
              {expanded.has(test.id) && test.detail && (
                <tr className="bg-gray-900">
                  <td colSpan={5} className="px-6 py-3">
                    <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap">
                      {typeof test.detail === "string"
                        ? test.detail
                        : JSON.stringify(test.detail, null, 2)}
                    </pre>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Behavioral Test Output Viewer

```tsx
export function BehavioralTestViewer({ test }: { test: BehavioralTestResult }) {
  return (
    <div className="rounded-xl border border-amber-700 bg-amber-900/10 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-amber-300 font-medium">{test.description}</span>
        <span className={test.passed ? "text-emerald-400" : "text-red-400"}>
          {test.passed ? "✅ PASS" : "❌ FAIL"}
        </span>
      </div>

      {test.stdout_diff?.length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-gray-400 mb-1">stdout diff (COBOL vs Java):</div>
          <div className="font-mono text-xs bg-gray-950 rounded p-3 space-y-1">
            {test.stdout_diff.map((d, i) => (
              <div key={i} className="grid grid-cols-[auto_1fr_1fr] gap-3">
                <span className="text-gray-500">L{d.line}</span>
                <span className="text-red-400 line-through">{d.cobol}</span>
                <span className="text-emerald-400">{d.java}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {test.assertion_failures?.length > 0 && (
        <div className="mt-3 space-y-1">
          {test.assertion_failures.map((f, i) => (
            <div key={i} className="text-xs text-red-400 font-mono">{f}</div>
          ))}
        </div>
      )}

      {test.java_stdout && (
        <details className="mt-3">
          <summary className="text-xs text-gray-400 cursor-pointer">Java stdout</summary>
          <pre className="text-xs text-gray-300 font-mono mt-2 bg-gray-950 p-2 rounded
                          max-h-40 overflow-y-auto whitespace-pre-wrap">
            {test.java_stdout}
          </pre>
        </details>
      )}
    </div>
  );
}
```

---

## SHARED COMPONENTS

### Monaco Editor Wrapper

```tsx
import Editor from "@monaco-editor/react";

export function CobolEditor({
  value, onChange, readOnly = false, language = "plaintext"
}: {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  language?: string;
}) {
  return (
    <div className="h-full rounded-xl overflow-hidden border border-gray-700">
      <Editor
        height="100%"
        language={language}
        theme="vs-dark"
        value={value}
        onChange={v => onChange?.(v ?? "")}
        options={{
          readOnly,
          fontSize: 13,
          fontFamily: "JetBrains Mono, Fira Code, monospace",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          lineNumbers: "on",
          renderWhitespace: "boundary",
          padding: { top: 12, bottom: 12 }
        }}
      />
    </div>
  );
}
```

### Loading State with Stage Progress

```tsx
export function PipelineProgress({
  currentStage,
  mode
}: {
  currentStage: string;
  mode: PipelineMode;
}) {
  const STAGES_FOR_MODE: Record<PipelineMode, string[]> = {
    full:          ["COPY Resolve", "Parse", "Analyse", "Segment", "Convert", "Test"],
    parse_only:    ["COPY Resolve", "Parse"],
    parse_analyse: ["COPY Resolve", "Parse", "Analyse"],
    analyse_only:  ["Analyse"],
    no_parse:      ["Convert"],
  };
  const stages = STAGES_FOR_MODE[mode];

  return (
    <div className="flex items-center gap-3 px-4 py-3 bg-gray-900 rounded-lg
                    border border-gray-700">
      <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent
                      rounded-full animate-spin" />
      <div className="flex items-center gap-2">
        {stages.map((s, i) => (
          <React.Fragment key={s}>
            <span className={`text-xs font-mono ${
              s === currentStage
                ? "text-violet-300 font-bold"
                : stages.indexOf(s) < stages.indexOf(currentStage)
                ? "text-emerald-400"
                : "text-gray-600"
            }`}>
              {s}
            </span>
            {i < stages.length - 1 && (
              <span className="text-gray-700">→</span>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
```

---

## CHECKLIST — Frontend

- [ ] Single File page: Monaco input + Monaco output + stage tabs with color coding
- [ ] Pipeline mode selector: 5 modes with descriptions and color badges
- [ ] Project page: drag-drop ZIP upload working
- [ ] File Explorer: IDE-style folder/file tree with type-based color coding
- [ ] File viewer: Monaco with syntax highlight for selected file
- [ ] Project results table: per-file status for each pipeline stage
- [ ] Download single Java file from results table
- [ ] Download all as ZIP button
- [ ] Testing page: 4 suite cards + pipeline status bar + detail table
- [ ] Behavioral test viewer: stdout diff with COBOL (red) vs Java (green) colors
- [ ] Test row expandable for detail
- [ ] PipelineProgress shows current stage during execution
- [ ] No mock data — all API calls to real backend endpoints
- [ ] All colors use defined design system palette

---

*Frontend Overhaul Prompt — 2026-04-23*
