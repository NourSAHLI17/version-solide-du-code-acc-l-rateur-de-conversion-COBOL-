# Segmenter Layer: Context-Aware Code Slicing

Implementation: `CobolSegmenter` in `app/services/segmenter.py`, used by `AnalysisAgent`
and the conversion constrained-generation path.

## 1. Purpose

The Segmenter acts as a bridge between the raw text and the high-level analysis. It "slices" the monolithic COBOL program into logical units (paragraphs) and enriches those segments with local data-flow information.

## 2. Methodology

### Paragraph Scoping
Instead of arbitrary line-length chunking, the Segmenter identifies paragraph boundaries (e.g., `MAIN-PROCEDURE.`, `ERROR-HANDLER.`). Each slice represents one cohesive logic block.

### Symbol Reference Extraction
For every segment, the Segmenter performs a shallow scan to identify:
- **Reads**: Variables read by the paragraph (used as inputs).
- **Writes**: Variables modified by the paragraph (used as outputs).
- **File I/O**: Detection of `READ`, `WRITE`, `REWRITE` operations.
- **Loops/Branches**: Identification of internal control flow complexity.

## 3. Rationale: Why Segment?

1. **Context Density**: By providing the Analysis Agent with the source of a *single* paragraph along with its specific inputs/outputs, the AI can focus its reasoning without being "distracted" by the rest of the 5,000-line file.
2. **Infinite Scale**: Large programs are analyzed paragraph-by-paragraph. The final analysis is then aggregated. This allows the system to handle programs of any size.
3. **Data-Flow Grounding**: By explicitly telling the AI "this paragraph reads X and writes Y", we prevent it from guessing variable purpose.

## 4. Segment Schema

Each `segment` object contains:
- `paragraph_name`: Literal COBOL name.
- `source_lines`: The raw text of the paragraph.
- `symbol_reads`: List of identifiers read.
- `symbol_writes`: List of identifiers modified.
- `has_file_io`: Boolean flag.
- `has_loop`: Boolean flag.

## 5. Input Detection Logic

The Segmenter is semi-intelligent. It knows that:
- A subject in an `EVALUATE` statement is a **read**.
- A target in a `MOVE` statement is a **write**.
- A variable used in an `IF` condition is a **read**.
- A subscript index (e.g., `I` in `TABLE(I)`) is a **read**.
