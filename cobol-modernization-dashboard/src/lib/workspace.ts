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
    validationResult: null,
    backendStatus: null,
    lastError: null,
    expectedOutput: DEFAULT_EXPECTED_OUTPUT,
    actualOutput: DEFAULT_ACTUAL_OUTPUT,
  };
}

export function useWorkspace() {
  const [workspace, setWorkspace] = useState<StoredWorkspace>(() => {
    if (typeof window === "undefined") {
      return defaultWorkspace();
    }

    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return defaultWorkspace();
    }

    try {
      const parsed = JSON.parse(raw) as StoredWorkspace;
      return { ...defaultWorkspace(), ...parsed };
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
      return defaultWorkspace();
    }
  });

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
  }, [workspace]);

  const actions = useMemo(
    () => ({
      setSourceCode(sourceCode: string) {
        setWorkspace((current) => ({ ...current, sourceCode, lastError: null }));
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

  return { workspace, actions };
}
