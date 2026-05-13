/** Extract PROGRAM-ID from COBOL source (first match, normalized). */
export function extractProgramId(sourceCode: string): string {
  const m = sourceCode.match(/\bPROGRAM-ID\.\s*([A-Z0-9-]+)/i);
  return m ? m[1].toUpperCase() : "UNKNOWN";
}
