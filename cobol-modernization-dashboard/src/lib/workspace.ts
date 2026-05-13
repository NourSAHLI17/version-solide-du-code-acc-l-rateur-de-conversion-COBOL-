"use client";

import { useEffect, useMemo, useState } from "react";

import { DEFAULT_ACTUAL_OUTPUT, DEFAULT_EXPECTED_OUTPUT, SAMPLE_COBOL } from "@/lib/demo";
import type { AnalysisResult, BackendStatus, ParserResult, PipelineWorkspace, ValidationResult } from "@/lib/types";

const STORAGE_KEY = "cobol-modernization-workspace";

interface StoredWorkspace extends PipelineWorkspace {
  expectedOutput: string;
  actualOutput: string;
}

function defaultWorkspace(): StoredWorkspace {
  return {
    sourceCode: SAMPLE_COBOL,
    parserResult: null,
    analysisResult: null,
    javaCode: "",
    projectResults: [],
    jclManifest: null,
    validationResult: null,
    backendStatus: null,
    lastError: null,
    expectedOutput: DEFAULT_EXPECTED_OUTPUT,
    actualOutput: DEFAULT_ACTUAL_OUTPUT,
  };
}

export function useWorkspace() {
  const [workspace, setWorkspace] = useState<StoredWorkspace>(defaultWorkspace);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        setHydrated(true);
        return;
      }

      try {
        const parsed = JSON.parse(raw) as StoredWorkspace;
        setWorkspace({ ...defaultWorkspace(), ...parsed });
      } catch {
        window.localStorage.removeItem(STORAGE_KEY);
      } finally {
        setHydrated(true);
      }
    }, 0);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => {
    if (!hydrated) {
      return;
    }

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
  }, [hydrated, workspace]);

  const actions = useMemo(
    () => ({
      setSourceCode(sourceCode: string) {
        setWorkspace((current) => ({
          ...current,
          sourceCode,
          lastError: null,
          // Invalidate downstream artifacts so analysis is not shown for the wrong program text.
          parserResult: null,
          analysisResult: null,
          javaCode: "",
        }));
      },
      setParserResult(parserResult: ParserResult) {
        setWorkspace((current) => ({ ...current, parserResult, lastError: null }));
      },
      setAnalysisResult(analysisResult: AnalysisResult) {
        setWorkspace((current) => ({ ...current, analysisResult, lastError: null }));
      },
      setJavaCode(javaCode: string) {
        setWorkspace((current) => ({ ...current, javaCode, lastError: null }));
      },
      setProjectResults(projectResults: Array<Record<string, unknown>>) {
        setWorkspace((current) => ({ ...current, projectResults, lastError: null }));
      },
      setActiveArtifact(sourceCode: string, parserResult: ParserResult, analysisResult: AnalysisResult, javaCode: string) {
        setWorkspace((current) => ({
          ...current,
          sourceCode,
          parserResult,
          analysisResult,
          javaCode,
          lastError: null,
        }));
      },
      setValidationResult(validationResult: ValidationResult) {
        setWorkspace((current) => ({ ...current, validationResult, lastError: null }));
      },
      setBackendStatus(backendStatus: BackendStatus | null) {
        setWorkspace((current) => ({ ...current, backendStatus, lastError: null }));
      },
      setExpectedOutput(expectedOutput: string) {
        setWorkspace((current) => ({ ...current, expectedOutput }));
      },
      setActualOutput(actualOutput: string) {
        setWorkspace((current) => ({ ...current, actualOutput }));
      },
      setLastError(lastError: string | null) {
        setWorkspace((current) => ({ ...current, lastError }));
      },
      reset() {
        setWorkspace(defaultWorkspace());
      },
    }),
    [],
  );

  return { workspace, actions, hydrated };
}
