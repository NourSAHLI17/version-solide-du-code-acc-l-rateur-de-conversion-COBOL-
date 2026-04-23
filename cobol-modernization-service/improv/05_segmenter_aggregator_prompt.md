# Codex Prompt — Segmentation, Chunking & Aggregation Layers
**Components:** Segmenter · Chunking Layer · Aggregator
**Language:** Python 3.10+
**Position in Pipeline:** Stage 5 (Segmenter/Chunker) · Stage 8 (Aggregator)

---

## SYSTEM PROMPT

You are implementing the segmentation, chunking, and aggregation layers of a
COBOL-to-Java modernization pipeline. These three components are the backbone
that enables the pipeline to handle programs of any size by converting them
segment-by-segment instead of in one monolithic LLM call.

All three components are fully deterministic — no LLM calls.

---

## COMPONENT 1: SEGMENTER

### Purpose
Group COBOL paragraphs into coherent, self-contained conversion units.
Each segment must be small enough for a reliable single LLM conversion call
and semantically complete (no dangling references).

### Segmentation Rules

1. **Start from entry point** — walk the call graph depth-first from the first paragraph
2. **Group tightly coupled paragraphs** — if a paragraph has exactly one caller,
   include it in the caller's segment
3. **Isolate shared paragraphs** — if a paragraph is called from 2+ segments, give it its own segment
4. **Never split across loop boundaries** — a PERFORM VARYING and all its inline content = one segment
5. **Data Division is always Segment 0** — symbol table declarations are a separate first segment

```python
from dataclasses import dataclass, field as dc_field

@dataclass
class Segment:
    id: str
    paragraphs: list[str]
    reads: set[str]
    writes: set[str]
    calls: list[str]          # paragraph names this segment calls
    called_by: list[str]      # paragraph names that call into this segment
    business_rules: list[str]
    complexity: str           # "low" | "medium" | "high"
    requires_chunking: bool   # True if complexity == "high"

def build_call_graph(calls: list[dict]) -> dict[str, list[str]]:
    graph = {}
    for call in calls:
        graph.setdefault(call['from'], []).append(call['to'])
    return graph

def build_reverse_graph(calls: list[dict]) -> dict[str, list[str]]:
    reverse = {}
    for call in calls:
        reverse.setdefault(call['to'], []).append(call['from'])
    return reverse

def segment_program(parser_output: dict, analysis_output: dict) -> list[Segment]:
    call_graph    = build_call_graph(parser_output['control_flow']['calls'])
    reverse_graph = build_reverse_graph(parser_output['control_flow']['calls'])
    para_order    = parser_output['paragraphs']
    operations    = parser_output['operations']
    symbol_table  = {s['name']: s for s in parser_output['symbol_table']}

    segments = []
    visited  = set()
    groups   = []

    def walk(paragraph: str, group: list[str]):
        if paragraph in visited:
            return
        visited.add(paragraph)
        group.append(paragraph)
        for callee in call_graph.get(paragraph, []):
            callers = reverse_graph.get(callee, [])
            if len(callers) == 1:
                walk(callee, group)  # tightly coupled — same segment
            else:
                if callee not in visited:
                    new_group = []
                    groups.append(new_group)
                    walk(callee, new_group)  # shared — own segment

    # Segment 0: Data Division
    segments.append(Segment(
        id="SEG_DATA",
        paragraphs=[],
        reads=set(), writes=set(), calls=[], called_by=[],
        business_rules=["Data Division — symbol declarations only"],
        complexity="low",
        requires_chunking=False
    ))

    # Walk procedure division
    entry = para_order[0]
    entry_group = []
    groups.append(entry_group)
    walk(entry, entry_group)

    for group in groups:
        if not group:
            continue
        reads, writes = extract_symbol_io(group, operations, symbol_table)
        complexity = score_complexity(group, parser_output)
        seg = Segment(
            id=f"SEG_{'_'.join(group[:2])}",
            paragraphs=group,
            reads=reads,
            writes=writes,
            calls=[c['to'] for c in parser_output['control_flow']['calls']
                   if c['from'] in group],
            called_by=[c['from'] for c in parser_output['control_flow']['calls']
                       if c['to'] in group],
            business_rules=get_rules_for(group, analysis_output),
            complexity=complexity,
            requires_chunking=(complexity == "high")
        )
        segments.append(seg)

    return segments

def score_complexity(paragraphs: list[str], parser_output: dict) -> str:
    score = 0
    score += len([l for l in parser_output['control_flow']['loops']
                  if l['paragraph'] in paragraphs]) * 3
    score += len([b for b in parser_output['control_flow']['branches']
                  if b['paragraph'] in paragraphs]) * 2
    score += len([o for o in parser_output['operations']
                  if o['paragraph'] in paragraphs]) * 0.5
    if score < 5:  return "low"
    if score < 15: return "medium"
    return "high"

def extract_symbol_io(paragraphs, operations, symbol_table):
    reads, writes = set(), set()
    para_set = set(paragraphs)
    for op in operations:
        if op['paragraph'] not in para_set:
            continue
        if op['type'] == 'MOVE':
            if op.get('value') in symbol_table:
                reads.add(op['value'])
            if op.get('target') in symbol_table:
                writes.add(op['target'])
        elif op['type'] == 'ACCEPT':
            if op.get('target') in symbol_table:
                writes.add(op['target'])
        elif op['type'] == 'DISPLAY':
            for ref in op.get('references', []):
                if ref in symbol_table:
                    reads.add(ref)
    return reads, writes
```

---

## COMPONENT 2: CHUNKING LAYER

### Purpose
Further divide segments marked `requires_chunking=True` into smaller chunks
that respect loop and branch boundaries.

### Chunking Rules

1. **Never cut inside a `PERFORM VARYING` block** — start/end must be in same chunk
2. **Never split `EVALUATE` or `IF/ELSE/END-IF`** — must be in same chunk
3. **Each chunk carries a symbol context header** — variables it reads/writes
4. **Cross-chunk dependencies** — variables written in chunk A and read in chunk B
   must be declared as `shared_state` in the segment manifest

```python
@dataclass
class Chunk:
    id: str
    segment_id: str
    paragraphs: list[str]    # subset of parent segment's paragraphs
    reads: set[str]
    writes: set[str]
    shared_with_chunks: list[str]  # chunk IDs that share state

def chunk_segment(segment: Segment, parser_output: dict) -> list[Chunk]:
    if not segment.requires_chunking:
        # Return single chunk = entire segment
        return [Chunk(
            id=f"{segment.id}_CHUNK_0",
            segment_id=segment.id,
            paragraphs=segment.paragraphs,
            reads=segment.reads,
            writes=segment.writes,
            shared_with_chunks=[]
        )]

    # Split by paragraph, respecting boundaries
    chunks = []
    current_paras = []
    TARGET_CHUNK_SIZE = 5  # paragraphs per chunk (adjust based on paragraph complexity)

    loop_para_set = {l['paragraph'] for l in parser_output['control_flow']['loops']}
    branch_para_set = {b['paragraph'] for b in parser_output['control_flow']['branches']}

    for para in segment.paragraphs:
        current_paras.append(para)
        # Can only cut AFTER this paragraph if:
        # 1. Not inside a loop paragraph
        # 2. Not inside a branch paragraph
        # 3. Reached target chunk size
        can_cut = (
            len(current_paras) >= TARGET_CHUNK_SIZE and
            para not in loop_para_set and
            para not in branch_para_set
        )
        if can_cut:
            reads, writes = extract_symbol_io(
                current_paras, parser_output['operations'],
                {s['name']: s for s in parser_output['symbol_table']}
            )
            chunks.append(Chunk(
                id=f"{segment.id}_CHUNK_{len(chunks)}",
                segment_id=segment.id,
                paragraphs=current_paras.copy(),
                reads=reads, writes=writes,
                shared_with_chunks=[]
            ))
            current_paras = []

    # Remaining paragraphs
    if current_paras:
        reads, writes = extract_symbol_io(
            current_paras, parser_output['operations'],
            {s['name']: s for s in parser_output['symbol_table']}
        )
        chunks.append(Chunk(
            id=f"{segment.id}_CHUNK_{len(chunks)}",
            segment_id=segment.id,
            paragraphs=current_paras,
            reads=reads, writes=writes,
            shared_with_chunks=[]
        ))

    # Identify cross-chunk shared state
    for i, chunk_a in enumerate(chunks):
        for j, chunk_b in enumerate(chunks):
            if i >= j: continue
            shared = chunk_a.writes & chunk_b.reads
            if shared:
                chunk_a.shared_with_chunks.append(chunk_b.id)
                chunk_b.shared_with_chunks.append(chunk_a.id)

    return chunks
```

---

## COMPONENT 3: AGGREGATOR

### Purpose
Reassemble all independently converted Java method fragments into a single
coherent, compilable Java class.

### Aggregation Rules

1. **Deduplicate field declarations** — same symbol name declared once only
2. **Type reconciliation** — BigDecimal > String > int > double (priority order)
3. **Shared state → instance fields** — variables written in one segment,
   read in another, must be instance fields (not local variables)
4. **Cross-reference validation** — every method call in any segment has a
   matching method body in another segment
5. **Constructor initialisation** — all VALUE clauses must be applied in constructor

```python
TYPE_PRIORITY = {"BigDecimal": 4, "String": 3, "int": 2, "long": 1, "double": 0}

def reconcile_type(type_a: str, type_b: str) -> str:
    return type_a if TYPE_PRIORITY.get(type_a, 0) >= TYPE_PRIORITY.get(type_b, 0) else type_b

def aggregate_segments(converted_segments: list[dict],
                        parser_output: dict,
                        analysis_output: dict) -> str:

    symbol_table = {s['name']: s for s in parser_output['symbol_table']}

    # ── Step 1: Collect + deduplicate field declarations ─────────────
    all_fields = {}
    for seg in converted_segments:
        for field in seg.get('declared_fields', []):
            name = field['java_name']
            if name in all_fields:
                existing = all_fields[name]
                all_fields[name]['java_type'] = reconcile_type(
                    existing['java_type'], field['java_type']
                )
                all_fields[name]['size'] = max(
                    existing.get('size', 0), field.get('size', 0)
                )
            else:
                all_fields[name] = field.copy()

    # ── Step 2: Identify shared state ────────────────────────────────
    all_writes = {}
    all_reads  = {}
    for seg in converted_segments:
        for sym in seg.get('writes', []):
            all_writes.setdefault(sym, []).append(seg['id'])
        for sym in seg.get('reads', []):
            all_reads.setdefault(sym, []).append(seg['id'])

    shared_state = {
        sym for sym in all_writes
        if len(set(all_writes.get(sym, [])) |
               set(all_reads.get(sym, []))) > 1
    }
    for java_name, field in all_fields.items():
        cobol_name = field.get('cobol_name', '').upper()
        if cobol_name in shared_state:
            all_fields[java_name]['scope'] = 'instance'
        else:
            all_fields[java_name].setdefault('scope', 'local')

    # ── Step 3: Validate cross-references ────────────────────────────
    all_method_names = {seg['method_name'] for seg in converted_segments
                        if seg.get('method_name')}
    cross_ref_errors = []
    for seg in converted_segments:
        for call in seg.get('outbound_calls', []):
            if call not in all_method_names:
                cross_ref_errors.append(
                    f"Segment {seg['id']} calls '{call}' but no segment defines it"
                )
    if cross_ref_errors:
        raise AggregationError("Cross-reference validation failed", cross_ref_errors)

    # ── Step 4: Assemble Java class ───────────────────────────────────
    instance_fields = [f for f in all_fields.values() if f.get('scope') == 'instance']
    imports = collect_imports(all_fields, converted_segments)
    class_name = to_java_class_name(parser_output['program_name'])
    package = "com.modernized." + parser_output['program_name'].lower().replace('-', '')

    return render_java_class(
        package=package,
        class_name=class_name,
        imports=imports,
        instance_fields=instance_fields,
        constructor_init=build_constructor(instance_fields, symbol_table),
        methods=[seg['java_method_body'] for seg in converted_segments],
    )

def to_java_class_name(cobol_name: str) -> str:
    # INVENTORY-MANAGEMENT → InventoryManagement
    return ''.join(word.capitalize() for word in cobol_name.split('-'))
```

---

## SEGMENT MANIFEST JSON CONTRACT

```json
{
  "program_name": "INVENTORY-MANAGEMENT",
  "segments": [
    {
      "id": "SEG_DATA",
      "paragraphs": [],
      "reads": [],
      "writes": [],
      "calls": [],
      "called_by": [],
      "business_rules": ["Data Division — symbol declarations only"],
      "complexity": "low",
      "requires_chunking": false
    },
    {
      "id": "SEG_MAIN-PARAGRAPH_DISPLAY-MENU",
      "paragraphs": ["MAIN-PARAGRAPH", "DISPLAY-MENU", "PROCESS-CHOICE"],
      "reads": ["MENU-CHOICE"],
      "writes": ["MENU-CHOICE"],
      "calls": ["ADD-ITEM", "UPDATE-ITEM", "DELETE-ITEM", "GENERATE-REPORTS"],
      "called_by": [],
      "business_rules": ["Routes execution based on user choice"],
      "complexity": "medium",
      "requires_chunking": false
    }
  ],
  "shared_state": ["MENU-CHOICE", "FOUND-FLAG", "INV-NAME", "INV-QUANTITY", "INV-PRICE"]
}
```

---

## CHECKLIST

### Segmenter
- [ ] Segment 0 is always Data Division (symbol declarations)
- [ ] Entry point walk starts from first paragraph in `paragraphs[]`
- [ ] Tightly coupled paragraphs (1 caller) grouped into same segment
- [ ] Shared paragraphs (2+ callers) get their own segment
- [ ] Complexity scored deterministically (no LLM)
- [ ] `requires_chunking=True` when complexity == "high"

### Chunker
- [ ] Segments with `requires_chunking=False` returned as single chunk
- [ ] Loop paragraphs never split across chunk boundary
- [ ] Branch paragraphs never split across chunk boundary
- [ ] Cross-chunk shared state identified and flagged

### Aggregator
- [ ] No duplicate field declarations in final Java class
- [ ] Type reconciliation: BigDecimal > String > int > double
- [ ] Shared-state variables promoted to instance fields
- [ ] All method calls validated against method body inventory
- [ ] Constructor initialises all instance fields per VALUE clause
- [ ] `AggregationError` raised on any unresolvable cross-reference

---

*Codex Prompt: Segmenter · Chunker · Aggregator — 2026-04-22*
