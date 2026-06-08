"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import TestingDiffPanel from "@/components/testing/TestingDiffPanel";
import TestingFailedTestsPanel from "@/components/testing/TestingFailedTestsPanel";
import TestingFailurePanel from "@/components/testing/TestingFailurePanel";
import TestingRetryOutcomePanel from "@/components/testing/TestingRetryOutcomePanel";
import TestingRunList from "@/components/testing/TestingRunList";
import TestingScenarioPanel from "@/components/testing/TestingScenarioPanel";
import TestingBusinessRulesPanel from "@/components/testing/TestingBusinessRulesPanel";
import TestingEdgeCasePanel from "@/components/testing/TestingEdgeCasePanel";
import TestingUnitTestPanel from "@/components/testing/TestingUnitTestPanel";
import TestingSummaryBar from "@/components/testing/TestingSummaryBar";
import TestingLayeredScoringPanel from "@/components/testing/TestingLayeredScoringPanel";
import TestingDecisionPanel from "@/components/testing/TestingDecisionPanel";
import TestingExportPdfButton from "@/components/testing/TestingExportPdfButton";
import TestingExportProjectPdfButton from "@/components/testing/TestingExportProjectPdfButton";
import TestingToolchainBanner from "@/components/testing/TestingToolchainBanner";
import type {
  RetryScopeMeta,
  TestingAgentRunResult,
  TestingFinalDecisionResult,
  TestingRetryResult,
  TestingTargetType,
  ToolchainGuidance,
} from "@/lib/testingAgentTypes";
import { targetModeLabel } from "@/lib/testingAgentTypes";
import type { BusinessRulesTestResult, EdgeCaseTestResult, UnitTestResult } from "@/lib/testingService";
import {
  buildFinalDecision,
  computeLocalFinalDecision,
  type FinalDecisionPayload,
  deriveRetryScope,
  findRunById,
  generateBusinessRulesTests,
  generateEdgeCaseTests,
  generateUnitTests,
  getWorkspaceArtifactsForEdgeCaseGen,
  getWorkspaceArtifactsForRetry,
  getWorkspaceArtifactsForRulesGen,
  getWorkspaceArtifactsForUnitGen,
  loadMockRuns,
  loadPersistedTestingSession,
  loadTestingTargetMode,
  persistTestingSession,
  persistTestingTargetMode,
  prependRun,
  retryConversionScope,
  getValidationArtifactReadiness,
  hydrateRunForDisplay,
  resolveDisplayRun,
  withEffectiveBehavioralFields,
  runBehavioralTestForMode,
  fetchToolchainGuidance,
  contactAdminToolchainGuidance,
  loadCachedValidationResults,
  loadTestingFallbackMode,
  persistCachedValidationResults,
  persistTestingFallbackMode,
  resolveRunFallbackMode,
  validationCacheScopeKey,
} from "@/lib/testingService";
import { restoreWorkspaceFromHistory } from "@/lib/historyTestingRestore";
import { loadSingleWorkspace } from "@/lib/singleFileWorkspace";
import { consumeTestingLaunch, type TestingLaunchSource } from "@/lib/testingLaunch";
import {
  buildHistoryEntryFromTestingRun,
  historyEntryToTestingRun,
  mergeRunsByRecency,
  persistenceMapFromHistoryEntries,
  testingRunToListItem,
} from "@/lib/testingHistoryBridge";
import {
  isDurablePersistence,
  persistenceHintForState,
  type DurableTestingPersistenceState,
  type TestingRunPersistenceState,
} from "@/lib/testingRunPersistence";
import type { HistoryEntry } from "@/services/historyService";
import * as historyService from "@/services/historyService";

export default function TestingAgentPage() {
  const [runs, setRuns] = useState<TestingAgentRunResult[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [targetMode, setTargetMode] = useState<TestingTargetType>("single_file");
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [scriptedInput, setScriptedInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usingMockFallback, setUsingMockFallback] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [brTestResult, setBrTestResult] = useState<BusinessRulesTestResult | null>(null);
  const [brTestLoading, setBrTestLoading] = useState(false);
  const [brTestError, setBrTestError] = useState<string | null>(null);
  const [ecTestResult, setEcTestResult] = useState<EdgeCaseTestResult | null>(null);
  const [ecTestLoading, setEcTestLoading] = useState(false);
  const [ecTestError, setEcTestError] = useState<string | null>(null);
  const [unitTestResult, setUnitTestResult] = useState<UnitTestResult | null>(null);
  const [unitTestLoading, setUnitTestLoading] = useState(false);
  const [unitTestError, setUnitTestError] = useState<string | null>(null);
  const [derivedRetryScope, setDerivedRetryScope] = useState<RetryScopeMeta | null>(null);
  const [scopeLoading, setScopeLoading] = useState(false);
  const [retryLoading, setRetryLoading] = useState(false);
  const [retryResult, setRetryResult] = useState<TestingRetryResult | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [runValidationLoop, setRunValidationLoop] = useState(false);
  const [saveStableLoading, setSaveStableLoading] = useState(false);
  const [finalDecision, setFinalDecision] = useState<TestingFinalDecisionResult | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [replaySource, setReplaySource] = useState<TestingLaunchSource | null>(null);
  const [fallbackMode, setFallbackMode] = useState(false);
  const [toolchainGuidance, setToolchainGuidance] = useState<ToolchainGuidance | null>(null);
  const [toolchainLoading, setToolchainLoading] = useState(true);
  const [showToolchainSetup, setShowToolchainSetup] = useState(false);
  const [sidebarLoading, setSidebarLoading] = useState(true);
  const [persistenceByRunId, setPersistenceByRunId] = useState<Record<string, TestingRunPersistenceState>>({});
  const [reliabilityByRunId, setReliabilityByRunId] = useState<Record<string, number>>({});

  const refreshSidebarFromApi = useCallback(async () => {
    try {
      const entries = await historyService.getTestingSidebarAsync();
      const apiRuns = entries
        .map(historyEntryToTestingRun)
        .filter((r): r is TestingAgentRunResult => r != null);
      const apiPersistence = persistenceMapFromHistoryEntries(entries);
      const relMap: Record<string, number> = {};
      for (const e of entries) {
        if (e.reliability_score != null) relMap[e.id] = Math.round(Number(e.reliability_score));
      }
      setReliabilityByRunId((prev) => ({ ...relMap, ...prev }));
      setPersistenceByRunId((prevPersistence) => {
        const mergedPersistence = { ...prevPersistence, ...apiPersistence };
        setRuns((prevRuns) =>
          mergeRunsByRecency(
            prevRuns.filter((r) => mergedPersistence[r.run_id] === "session"),
            apiRuns,
          ),
        );
        return mergedPersistence;
      });
    } catch {
      /* sidebar stays on in-memory runs */
    }
  }, []);

  useEffect(() => {
    setTargetMode(loadTestingTargetMode());
    setFallbackMode(loadTestingFallbackMode());
    let cancelled = false;
    void (async () => {
      setSidebarLoading(true);
      try {
        const session = loadPersistedTestingSession();
        const entries = await historyService.getTestingSidebarAsync();
        if (cancelled) return;
        const apiRuns = entries
          .map(historyEntryToTestingRun)
          .filter((r): r is TestingAgentRunResult => r != null);
        const apiPersistence = persistenceMapFromHistoryEntries(entries);
        const relMap: Record<string, number> = { ...session.reliabilityByRunId };
        for (const e of entries) {
          if (e.reliability_score != null) relMap[e.id] = Math.round(Number(e.reliability_score));
        }
        const mergedPersistence = { ...session.persistence, ...apiPersistence };
        setPersistenceByRunId(mergedPersistence);
        setReliabilityByRunId(relMap);
        const merged = mergeRunsByRecency(session.sessionRuns, apiRuns);
        setRuns(merged);
        setSelectedRunId(merged[0]?.run_id ?? null);
      } catch {
        if (!cancelled) {
          const session = loadPersistedTestingSession();
          setPersistenceByRunId(session.persistence);
          setReliabilityByRunId(session.reliabilityByRunId);
          setRuns(session.sessionRuns);
          setSelectedRunId(session.sessionRuns[0]?.run_id ?? null);
        }
      } finally {
        if (!cancelled) {
          setSidebarLoading(false);
          setHydrated(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleModeChange = (mode: TestingTargetType) => {
    setTargetMode(mode);
    persistTestingTargetMode(mode);
    setSelectedFilePath(null);
    setError(null);
  };

  const listItems = useMemo(
    () =>
      runs.map((run) => {
        const persistence_state = persistenceByRunId[run.run_id] ?? "session";
        const reliability_score =
          reliabilityByRunId[run.run_id] ?? (run.qscore != null ? Math.round(Number(run.qscore)) : null);
        return testingRunToListItem(run, {
          force_save: persistence_state === "saved",
          persistence_state,
          reliability_score,
        });
      }),
    [runs, persistenceByRunId, reliabilityByRunId],
  );
  const selectedPersistence = selectedRunId ? persistenceByRunId[selectedRunId] : undefined;
  const selectedRun = useMemo(() => findRunById(runs, selectedRunId), [runs, selectedRunId]);

  useEffect(() => {
    if (!selectedRun?.file_results?.length) {
      setSelectedFilePath(null);
      return;
    }
    if (selectedFilePath && selectedRun.file_results.some((f) => f.path === selectedFilePath)) {
      return;
    }
    setSelectedFilePath(null);
  }, [selectedRun, selectedFilePath]);

  const displayRun = useMemo(() => {
    if (!selectedRun) return null;
    return resolveDisplayRun(selectedRun, selectedFilePath);
  }, [selectedRun, selectedFilePath]);

  const displayRunEffective = useMemo(() => {
    if (!selectedRun || !displayRun) return null;
    return withEffectiveBehavioralFields(selectedRun, displayRun, selectedFilePath);
  }, [selectedRun, displayRun, selectedFilePath]);

  const runView = displayRunEffective ?? displayRun;

  const rulesGenArtifacts = useMemo(
    () => getWorkspaceArtifactsForRulesGen(targetMode, selectedFilePath),
    [targetMode, selectedFilePath],
  );

  const edgeGenArtifacts = useMemo(
    () => getWorkspaceArtifactsForEdgeCaseGen(targetMode, selectedFilePath),
    [targetMode, selectedFilePath],
  );

  const unitGenArtifacts = useMemo(
    () => getWorkspaceArtifactsForUnitGen(targetMode, selectedFilePath),
    [targetMode, selectedFilePath],
  );

  const canGenerateBrTests = Boolean(
    selectedRun && rulesGenArtifacts?.hasAnalysis && rulesGenArtifacts.java_source?.trim(),
  );

  const canGenerateEdgeTests = Boolean(
    hydrated && edgeGenArtifacts?.hasParser && edgeGenArtifacts.java_source?.trim(),
  );

  const canGenerateUnitTests = Boolean(
    hydrated && unitGenArtifacts?.hasParser && unitGenArtifacts.java_source?.trim(),
  );

  const validationArtifacts = useMemo(
    () =>
      hydrated
        ? getValidationArtifactReadiness(targetMode, selectedFilePath)
        : { business_rules_ready: false, edge_cases_ready: false, unit_tests_ready: false },
    [hydrated, targetMode, selectedFilePath],
  );

  const restoreValidationFromCache = useCallback(() => {
    const cached = loadCachedValidationResults(targetMode);
    if (!cached) return;
    if (cached.business_rules) setBrTestResult(cached.business_rules);
    if (cached.edge_cases) setEcTestResult(cached.edge_cases);
    if (cached.unit_tests) setUnitTestResult(cached.unit_tests);
  }, [targetMode]);

  const persistRunToApi = useCallback(
    async (
      run: TestingAgentRunResult,
      options: {
        reliability_score?: number | null;
        persistence: DurableTestingPersistenceState;
        finalDecision?: TestingFinalDecisionResult | null;
      },
    ) => {
      const artifacts = getWorkspaceArtifactsForRetry(targetMode, selectedFilePath);
      const ws = targetMode === "single_file" ? loadSingleWorkspace() : null;
      const force_save = options.persistence === "saved";
      const entry = buildHistoryEntryFromTestingRun(run, {
        reliability_score:
          options.reliability_score ?? (run.qscore != null ? Math.round(Number(run.qscore)) : null),
        force_save,
        historyPersistence: options.persistence,
        finalDecision: options.finalDecision ?? null,
        parserOutput: (artifacts?.parser_json ?? {}) as HistoryEntry["parserOutput"],
        analysisOutput: (artifacts?.analysis_json ?? {}) as HistoryEntry["analysisOutput"],
        javaOutput: artifacts?.java_source ?? null,
        sourceCode: artifacts?.cobol_source,
        conversionScore: ws?.conversionScore ?? undefined,
      });
      await historyService.addAsync(entry);
      setPersistenceByRunId((prev) => ({ ...prev, [run.run_id]: options.persistence }));
    },
    [targetMode, selectedFilePath],
  );

  const applyRun = useCallback(
    (run: TestingAgentRunResult) => {
      const hydrated = hydrateRunForDisplay(run);
      setRuns((prev) => prependRun(prev, hydrated));
      setSelectedRunId(hydrated.run_id);
      setSelectedFilePath(null);
      setUsingMockFallback(false);
      setError(null);
      setRetryResult(null);
      setRetryError(null);
      setDerivedRetryScope(null);
      setFinalDecision(null);
      setDecisionError(null);
      restoreValidationFromCache();
      setPersistenceByRunId((prev) => ({ ...prev, [hydrated.run_id]: "session" }));
      if (hydrated.qscore != null) {
        setReliabilityByRunId((prev) => ({
          ...prev,
          [hydrated.run_id]: Math.round(Number(hydrated.qscore)),
        }));
      }
    },
    [restoreValidationFromCache],
  );

  useEffect(() => {
    if (!runView) {
      setFinalDecision(null);
      setDecisionError(null);
      return;
    }
    if (isDurablePersistence(persistenceByRunId[runView.run_id])) {
      return;
    }
    const artifacts = getWorkspaceArtifactsForRetry(targetMode, selectedFilePath);
    const decisionPayload = {
      program_name: runView.program_name,
      diff_summary: runView.diff_summary as unknown as Record<string, unknown>,
      failed_tests: runView.failed_tests as unknown as Array<Record<string, unknown>>,
      behavioral_status: runView.status,
      execution_mode: runView.execution_mode,
      fallback_mode: runView.fallback_mode,
      validation_artifacts: validationArtifacts,
      parser_json: artifacts?.parser_json ?? {},
      analysis_json: artifacts?.analysis_json ?? {},
      java_source: artifacts?.java_source ?? "",
      derive_retry_scope: true,
      business_rules_test_result: brTestResult as unknown as Record<string, unknown> | null,
      edge_case_test_result: ecTestResult as unknown as Record<string, unknown> | null,
      unit_test_result: unitTestResult as unknown as Record<string, unknown> | null,
      retry_scope: derivedRetryScope,
    };

    setFinalDecision(computeLocalFinalDecision(decisionPayload));

    let cancelled = false;
    setDecisionLoading(true);
    setDecisionError(null);
    void buildFinalDecision(decisionPayload as FinalDecisionPayload)
      .then((d) => {
        if (!cancelled) {
          setFinalDecision({
            ...d,
            retry_scope: d.retry_scope ?? derivedRetryScope ?? null,
          });
          setDecisionError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDecisionError(
            err instanceof Error
              ? `${err.message} Showing estimated score from run data.`
              : "API unavailable. Showing estimated score from run data.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setDecisionLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    runView,
    targetMode,
    selectedFilePath,
    brTestResult,
    ecTestResult,
    unitTestResult,
    validationArtifacts,
    derivedRetryScope,
    persistenceByRunId,
  ]);

  useEffect(() => {
    if (!runView?.run_id || finalDecision?.reliability_score == null) return;
    const score = Math.round(Number(finalDecision.reliability_score));
    setReliabilityByRunId((prev) => (prev[runView.run_id] === score ? prev : { ...prev, [runView.run_id]: score }));
  }, [runView?.run_id, finalDecision?.reliability_score]);

  useEffect(() => {
    if (!hydrated || usingMockFallback) return;
    persistTestingSession(runs, persistenceByRunId, reliabilityByRunId);
  }, [runs, persistenceByRunId, reliabilityByRunId, hydrated, usingMockFallback]);

  useEffect(() => {
    if (!selectedRunId || usingMockFallback) return;
    const state = persistenceByRunId[selectedRunId];
    if (!isDurablePersistence(state)) return;
    let cancelled = false;
    void historyService.getByIdAsync(selectedRunId).then((entry) => {
      if (cancelled || !entry) return;
      const savedRun = historyEntryToTestingRun(entry);
      if (!savedRun) return;
      setRuns((prev) => prev.map((r) => (r.run_id === selectedRunId ? savedRun : r)));
      const snapshot = entry.finalDecisionSnapshot;
      if (snapshot && typeof snapshot === "object") {
        setFinalDecision(snapshot as TestingFinalDecisionResult);
        setDecisionError(null);
      } else if (entry.reliability_score != null) {
        setFinalDecision({
          program_name: savedRun.program_name,
          reliability_score: Math.round(Number(entry.reliability_score)),
          decision_state: "trusted",
          save_eligible: true,
          blockers: [],
          is_local_estimate: true,
        });
        setDecisionError(null);
      }
      if (entry.reliability_score != null) {
        setReliabilityByRunId((prev) => ({
          ...prev,
          [selectedRunId]: Math.round(Number(entry.reliability_score)),
        }));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId, persistenceByRunId, usingMockFallback]);

  useEffect(() => {
    const linesCompared = runView?.diff_summary?.lines_compared ?? 0;
    if (
      !runView ||
      runView.status === "passed" ||
      runView.status === "not_run" ||
      linesCompared <= 0
    ) {
      setDerivedRetryScope(null);
      return;
    }
    const artifacts = getWorkspaceArtifactsForRetry(targetMode, selectedFilePath);
    if (!artifacts?.java_source?.trim()) {
      setDerivedRetryScope(null);
      return;
    }
    let cancelled = false;
    setScopeLoading(true);
    void deriveRetryScope({
      ...artifacts,
      failed_tests: runView.failed_tests as unknown as Array<Record<string, unknown>>,
      diff_summary: runView.diff_summary as unknown as Record<string, unknown>,
    })
      .then((scope) => {
        if (!cancelled) setDerivedRetryScope(scope);
      })
      .catch(() => {
        if (!cancelled) setDerivedRetryScope(null);
      })
      .finally(() => {
        if (!cancelled) setScopeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runView, targetMode, selectedFilePath]);

  const liveExecutionAvailable = toolchainGuidance?.live_execution_available ?? true;

  const runLiveTest = useCallback(async () => {
    setError(null);
    setUsingMockFallback(false);
    setLoading(true);
    try {
      const result = await runBehavioralTestForMode(targetMode, {
        scriptedInput,
        fallbackMode,
        liveExecutionAvailable,
      });
      applyRun(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Behavioral diff request failed.");
    } finally {
      setLoading(false);
    }
  }, [applyRun, fallbackMode, liveExecutionAvailable, scriptedInput, targetMode]);

  const refreshToolchainGuidance = useCallback(async () => {
    setToolchainLoading(true);
    try {
      const guidance = await fetchToolchainGuidance({
        fallbackMode,
        executionMode: runView?.execution_mode ?? selectedRun?.execution_mode,
        forceRefresh: true,
      });
      setToolchainGuidance(guidance);
    } catch (err) {
      setToolchainGuidance(
        contactAdminToolchainGuidance(
          err instanceof Error ? err.message : "Could not reach the testing API.",
        ),
      );
    } finally {
      setToolchainLoading(false);
    }
  }, [fallbackMode, runView?.execution_mode, selectedRun?.execution_mode]);

  useEffect(() => {
    if (!hydrated) return;
    void refreshToolchainGuidance();
  }, [hydrated, refreshToolchainGuidance]);

  useEffect(() => {
    if (!hydrated) return;
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void refreshToolchainGuidance();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [hydrated, refreshToolchainGuidance]);

  const handleFallbackModeChange = (enabled: boolean) => {
    setFallbackMode(enabled);
    persistTestingFallbackMode(enabled);
  };

  const scrollToResults = () => {
    document.querySelector("[data-testing-results]")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  useEffect(() => {
    if (!hydrated) return;
    const launch = consumeTestingLaunch();
    if (!launch?.autoRun) return;

    setTargetMode(launch.mode);
    persistTestingTargetMode(launch.mode);
    setReplaySource(launch.source ?? "conversion");
    setError(null);
    setUsingMockFallback(false);
    setLoading(true);

    let cancelled = false;
    void (async () => {
      try {
        if (launch.source === "history" && launch.historyId) {
          const entry = await historyService.getByIdAsync(launch.historyId);
          if (!entry) {
            throw new Error("Saved history entry not found. Refresh history and try again.");
          }
          const restored = restoreWorkspaceFromHistory(entry);
          if ("error" in restored) {
            throw new Error(restored.error);
          }
        }

        const result = await runBehavioralTestForMode(launch.mode, {
          scriptedInput: launch.scriptedInput ?? "",
          fallbackMode: resolveRunFallbackMode(
            loadTestingFallbackMode(),
            toolchainGuidance?.live_execution_available ?? true,
          ),
          liveExecutionAvailable: toolchainGuidance?.live_execution_available ?? true,
        });
        if (!cancelled) applyRun(result);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Behavioral diff request failed.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setReplaySource(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [hydrated, applyRun, toolchainGuidance?.live_execution_available]);

  useEffect(() => {
    if (!hydrated) return;
    restoreValidationFromCache();
  }, [hydrated, targetMode, restoreValidationFromCache]);

  const loadSampleRuns = useCallback(() => {
    const mock = loadMockRuns().map((r) => hydrateRunForDisplay(r));
    if (mock.length === 0) {
      setError("Sample data is unavailable.");
      return;
    }
    const sessionPersistence: Record<string, TestingRunPersistenceState> = {};
    for (const run of mock) {
      sessionPersistence[run.run_id] = "session";
    }
    setPersistenceByRunId(sessionPersistence);
    setRuns(mock);
    setSelectedRunId(mock[0]?.run_id ?? null);
    setSelectedFilePath(null);
    setUsingMockFallback(true);
    setError(null);
  }, []);

  const handleReset = useCallback(() => {
    setRuns([]);
    setSelectedRunId(null);
    setSelectedFilePath(null);
    setLoading(false);
    setError(null);
    setUsingMockFallback(false);
    setBrTestResult(null);
    setBrTestError(null);
    setEcTestResult(null);
    setEcTestError(null);
    setUnitTestResult(null);
    setUnitTestError(null);
    setFinalDecision(null);
    setDecisionError(null);
    setRetryResult(null);
    setRetryError(null);
    setDerivedRetryScope(null);
  }, []);

  const handleGenerateBrTests = useCallback(async () => {
    const artifacts = getWorkspaceArtifactsForRulesGen(targetMode, selectedFilePath);
    if (!artifacts?.hasAnalysis) {
      setBrTestError("Analysis JSON is required. Complete analysis on the conversion workspace first.");
      return;
    }
    if (!artifacts.java_source?.trim()) {
      setBrTestError("Java output is required to generate tests.");
      return;
    }
    setBrTestLoading(true);
    setBrTestError(null);
    try {
      const result = await generateBusinessRulesTests({
        program_name: artifacts.program_name,
        business_rules: artifacts.business_rules,
        java_source: artifacts.java_source,
      });
      setBrTestResult(result);
      const scope = validationCacheScopeKey(targetMode);
      if (scope) {
        persistCachedValidationResults({
          ...scope,
          business_rules: result,
          edge_cases: ecTestResult,
          unit_tests: unitTestResult,
        });
      }
    } catch (err) {
      setBrTestError(err instanceof Error ? err.message : "Business rules test generation failed.");
    } finally {
      setBrTestLoading(false);
    }
  }, [targetMode, selectedFilePath, ecTestResult, unitTestResult]);

  const handleGenerateEdgeTests = useCallback(async () => {
    const artifacts = getWorkspaceArtifactsForEdgeCaseGen(targetMode, selectedFilePath);
    if (!artifacts?.hasParser) {
      setEcTestError("Parser JSON is required. Complete parsing on the conversion workspace first.");
      return;
    }
    if (!artifacts.java_source?.trim()) {
      setEcTestError("Java output is required to generate edge-case tests.");
      return;
    }
    setEcTestLoading(true);
    setEcTestError(null);
    try {
      const result = await generateEdgeCaseTests({
        program_name: artifacts.program_name,
        parser_json: artifacts.parser_json,
        java_source: artifacts.java_source,
      });
      setEcTestResult(result);
      const scope = validationCacheScopeKey(targetMode);
      if (scope) {
        persistCachedValidationResults({
          ...scope,
          business_rules: brTestResult,
          edge_cases: result,
          unit_tests: unitTestResult,
        });
      }
    } catch (err) {
      setEcTestError(err instanceof Error ? err.message : "Edge-case test generation failed.");
    } finally {
      setEcTestLoading(false);
    }
  }, [targetMode, selectedFilePath, brTestResult, unitTestResult]);

  const handleGenerateUnitTests = useCallback(async () => {
    const artifacts = getWorkspaceArtifactsForUnitGen(targetMode, selectedFilePath);
    if (!artifacts?.hasParser) {
      setUnitTestError("Parser JSON is required. Complete parsing on the conversion workspace first.");
      return;
    }
    if (!artifacts.java_source?.trim()) {
      setUnitTestError("Java output is required to generate unit tests.");
      return;
    }
    setUnitTestLoading(true);
    setUnitTestError(null);
    try {
      const result = await generateUnitTests({
        program_name: artifacts.program_name,
        parser_json: artifacts.parser_json,
        analysis_json: artifacts.analysis_json,
        java_source: artifacts.java_source,
      });
      setUnitTestResult(result);
      const scope = validationCacheScopeKey(targetMode);
      if (scope) {
        persistCachedValidationResults({
          ...scope,
          business_rules: brTestResult,
          edge_cases: ecTestResult,
          unit_tests: result,
        });
      }
    } catch (err) {
      setUnitTestError(err instanceof Error ? err.message : "Unit test generation failed.");
    } finally {
      setUnitTestLoading(false);
    }
  }, [targetMode, selectedFilePath, brTestResult, ecTestResult]);

  const handleRetryScope = useCallback(async () => {
    if (!runView) return;
    const artifacts = getWorkspaceArtifactsForRetry(targetMode, selectedFilePath);
    if (!artifacts) {
      setRetryError("Workspace artifacts missing for retry.");
      return;
    }
    setRetryLoading(true);
    setRetryError(null);
    setRetryResult(null);
    try {
      const scope = derivedRetryScope;
      const result = await retryConversionScope({
        ...artifacts,
        failed_tests: runView.failed_tests as unknown as Array<Record<string, unknown>>,
        diff_summary: runView.diff_summary as unknown as Record<string, unknown>,
        scope_type: scope?.scope_type,
        scope_id: scope?.scope_id,
        run_id: runView.run_id,
        scripted_input: scriptedInput,
        run_validation_loop: runValidationLoop,
      });
      setRetryResult(result);
      if (result.reliability_score != null && result.decision_state) {
        setFinalDecision((prev) => ({
          program_name: result.program_name,
          reliability_score: result.reliability_score!,
          decision_state: result.decision_state!,
          save_eligible: Boolean(result.save_eligible),
          score_breakdown: result.score_breakdown ?? prev?.score_breakdown,
          reason_summary: result.reason_summary ?? prev?.reason_summary,
          blockers: result.blockers ?? prev?.blockers ?? [],
          diff_summary: prev?.diff_summary,
          test_summary: prev?.test_summary,
          retry_scope: result.retry_scope ?? prev?.retry_scope ?? null,
          is_local_estimate: false,
        }));
      }
      if (result.test_result) {
        setRuns((prev) => {
          const idx = prev.findIndex((r) => r.run_id === runView.run_id);
          if (idx < 0) return prev;
          const next = [...prev];
          next[idx] = result.test_result!;
          return next;
        });
      }
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : "Scoped retry failed.");
    } finally {
      setRetryLoading(false);
    }
  }, [runView, derivedRetryScope, runValidationLoop, scriptedInput, targetMode, selectedFilePath]);

  const handleManualSaveToHistory = useCallback(() => {
    if (!runView) return;
    setSaveStableLoading(true);
    void (async () => {
      try {
        const hydrated = hydrateRunForDisplay(runView);
        await persistRunToApi(hydrated, {
          reliability_score: finalDecision?.reliability_score,
          persistence: "saved",
          finalDecision,
        });
        setRuns((prev) => prependRun(prev, hydrated));
        if (finalDecision?.reliability_score != null) {
          setReliabilityByRunId((prev) => ({
            ...prev,
            [hydrated.run_id]: Math.round(Number(finalDecision.reliability_score)),
          }));
        }
        persistTestingSession(
          prependRun(runs, hydrated),
          { ...persistenceByRunId, [hydrated.run_id]: "saved" },
          reliabilityByRunId,
        );
        await refreshSidebarFromApi();
      } catch (err) {
        window.alert(err instanceof Error ? err.message : "Failed to save to history.");
      } finally {
        setSaveStableLoading(false);
      }
    })();
  }, [runView, finalDecision, persistRunToApi, refreshSidebarFromApi, runs, persistenceByRunId, reliabilityByRunId]);

  const handleSaveStableRun = useCallback(() => {
    const runToSave = retryResult?.test_result ?? runView;
    const gate = finalDecision
      ? {
          ready_to_save: finalDecision.save_eligible,
          save_state: finalDecision.decision_state,
        }
      : retryResult?.save_gate;
    if (!runToSave || !gate?.ready_to_save) return;
    setSaveStableLoading(true);
    void (async () => {
      try {
        const hydrated = hydrateRunForDisplay(runToSave);
        const persistence: DurableTestingPersistenceState = "stable_saved";
        await persistRunToApi(hydrated, {
          reliability_score: finalDecision?.reliability_score ?? retryResult?.reliability_score,
          persistence,
          finalDecision,
        });
        setRuns((prev) => prependRun(prev, hydrated));
        if (finalDecision?.reliability_score != null) {
          setReliabilityByRunId((prev) => ({
            ...prev,
            [hydrated.run_id]: Math.round(Number(finalDecision.reliability_score)),
          }));
        }
        persistTestingSession(
          prependRun(runs, hydrated),
          { ...persistenceByRunId, [hydrated.run_id]: persistence },
          reliabilityByRunId,
        );
        await refreshSidebarFromApi();
      } catch (err) {
        window.alert(err instanceof Error ? err.message : "Failed to save to history.");
      } finally {
        setSaveStableLoading(false);
      }
    })();
  }, [retryResult, runView, finalDecision, persistRunToApi, refreshSidebarFromApi, runs, persistenceByRunId, reliabilityByRunId]);

  const modeHint =
    targetMode === "project"
      ? "Uses per-file COBOL, Java, parser, and analysis from the Project conversion workspace."
      : "Uses COBOL source, Java output, parser, and analysis from the Single File conversion workspace.";

  const emptyHint =
    targetMode === "project"
      ? "No runs yet. Complete Project conversion, then run a behavioral test."
      : "No runs yet. Complete Single File conversion, then run a behavioral test.";

  return (
    <div
      className="testing-page"
      style={{ maxWidth: 1400, margin: "0 auto", padding: "24px", display: "flex", flexDirection: "column", gap: 18 }}
    >
      <header className="page-hero glass-card">
        <p className="hero-kicker">Stage 9 — Testing Agent</p>
        <h1>Testing</h1>
        <p className="hero-copy">
          Behavioral equivalence between COBOL and Java for a single program or a whole project. Run a test to compare
          stdout and inspect failure attribution from the backend.
        </p>
      </header>

      <TestingToolchainBanner
        guidance={toolchainGuidance}
        loading={toolchainLoading}
        showSetupDetails={showToolchainSetup}
        onRunTest={() => void runLiveTest()}
        onEnableFallback={() => handleFallbackModeChange(true)}
        onToggleSetup={() => setShowToolchainSetup((v) => !v)}
        onScrollToResults={scrollToResults}
      />

      <div className="glass-card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="panel-label">Run behavioral diff</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <span className="testing-summary-label">Target mode</span>
          {(["single_file", "project"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`action-button ${targetMode === mode ? "primary" : "secondary"}`}
              disabled={loading}
              onClick={() => handleModeChange(mode)}
            >
              {targetModeLabel(mode)}
            </button>
          ))}
          <span className="testing-panel-hint" style={{ margin: 0 }}>
            Active: <strong style={{ color: "#e5e7eb" }}>{targetModeLabel(targetMode)}</strong>
          </span>
        </div>
        <p className="testing-panel-hint" style={{ margin: 0 }}>
          {modeHint}
        </p>
        <label className="testing-fallback-toggle">
          <input
            type="checkbox"
            checked={fallbackMode}
            disabled={loading}
            onChange={(e) => handleFallbackModeChange(e.target.checked)}
          />
          <span>
            <strong style={{ color: "#e5e7eb" }}>Snapshot fallback</strong> — compare stored COBOL/Java stdout
            when live execution is unavailable (requires both snapshot outputs in the request).
          </span>
        </label>
        <label className="testing-stdin-label">
          <span className="testing-summary-label">Scripted stdin (optional)</span>
          <textarea
            className="app-input testing-stdin-field"
            rows={3}
            value={scriptedInput}
            onChange={(e) => setScriptedInput(e.target.value)}
            placeholder="e.g. menu choices and inputs sent to both programs…"
          />
        </label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          <button type="button" className="action-button primary" disabled={loading} onClick={() => void runLiveTest()}>
            {loading ? "Running diff…" : "Run behavioral test"}
          </button>
          <button type="button" className="action-button secondary" disabled={loading} onClick={handleReset}>
            🔄 Reset
          </button>
          <button type="button" className="action-button secondary" disabled={loading} onClick={loadSampleRuns}>
            Load sample data
          </button>
        </div>
      </div>

      {error && (
        <div className="glass-card error-banner" style={{ padding: 14 }}>
          {error}
          {!usingMockFallback && (
            <p className="testing-panel-hint" style={{ marginTop: 8, marginBottom: 0 }}>
              You can load sample data offline or complete the pipeline on {targetModeLabel(targetMode)} and try again.
            </p>
          )}
        </div>
      )}

      {usingMockFallback && (
        <div className="glass-card" style={{ padding: 12, color: "var(--text-muted)", fontSize: 13 }}>
          Showing sample runs (backend unavailable or demo mode). Live results replace these when a test succeeds.
        </div>
      )}

      {replaySource === "history" && loading ? (
        <div className="glass-card" style={{ padding: 12, color: "var(--text-muted)", fontSize: 13 }}>
          Running saved behavioral replay from history ({targetModeLabel(targetMode)})…
        </div>
      ) : null}

      {replaySource === "conversion" && loading ? (
        <div className="glass-card" style={{ padding: 12, color: "var(--text-muted)", fontSize: 13 }}>
          Running behavioral comparison from your conversion workspace ({targetModeLabel(targetMode)})…
        </div>
      ) : null}

      {loading && !replaySource ? (
        <div className="glass-card" style={{ padding: 12, color: "var(--text-muted)", fontSize: 13 }}>
          Running behavioral diff against the API ({targetModeLabel(targetMode)})…
        </div>
      ) : null}

      <TestingDecisionPanel
        decision={runView ? finalDecision : null}
        behavioralRunStatus={runView?.status}
        behavioralExecutionMode={runView?.execution_mode}
        behavioralLinesCompared={runView?.diff_summary?.lines_compared}
        layeredQscore={runView?.qscore}
        loading={Boolean(runView) && decisionLoading}
        error={decisionError}
        placeholder={
          listItems.length === 0
            ? "Run a behavioral test or load sample data to see whether you can trust this conversion."
            : !displayRun
              ? "Select a test run from the list to see reliability score and save eligibility."
              : undefined
        }
        onSaveToHistory={
          finalDecision?.save_eligible && runView ? handleSaveStableRun : undefined
        }
        onManualSaveToHistory={runView ? handleManualSaveToHistory : undefined}
        saving={saveStableLoading}
      />

      {targetMode === "single_file" && runView && selectedRun ? (
        <div className="glass-card" style={{ padding: 14, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
          <TestingExportPdfButton run={selectedRun} decision={finalDecision} />
          <p className="testing-panel-hint" style={{ margin: 0, flex: "1 1 200px" }}>
            Download a branded consulting-style PDF report for clients or auditors. Uses the saved history record when available.
          </p>
        </div>
      ) : null}

      {targetMode === "project" && selectedRun ? (
        <div className="glass-card" style={{ padding: 14, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
          <TestingExportProjectPdfButton run={selectedRun} decision={finalDecision} disabled={!selectedRun} />
          <p className="testing-panel-hint" style={{ margin: 0, flex: "1 1 200px" }}>
            Download a project-level PDF with per-program compile/execute status, diff summary, and stdout comparison.
          </p>
        </div>
      ) : null}

      {canGenerateEdgeTests ? (
        <TestingEdgeCasePanel
          hydrated={hydrated}
          result={ecTestResult}
          loading={ecTestLoading}
          error={ecTestError}
          canGenerate={canGenerateEdgeTests}
          onGenerate={() => void handleGenerateEdgeTests()}
        />
      ) : null}

      {canGenerateUnitTests ? (
        <TestingUnitTestPanel
          result={unitTestResult}
          loading={unitTestLoading}
          error={unitTestError}
          canGenerate={canGenerateUnitTests}
          onGenerate={() => void handleGenerateUnitTests()}
        />
      ) : null}

      <div className="testing-layout">
        <aside className="testing-sidebar glass-card">
          <TestingRunList runs={listItems} selectedRunId={selectedRunId} onSelect={setSelectedRunId} />
          <p className="testing-sidebar-note">
            {sidebarLoading
              ? "Loading saved runs from server…"
              : hydrated && listItems.length === 0
                ? emptyHint
                : "New test runs appear as Current session run until you save them. Saved and Stable saved runs persist in server history after refresh."}
          </p>
        </aside>

        <div className="testing-main" data-testing-results>
          {!selectedRun || !displayRun ? (
            <div className="glass-card testing-panel">
              <p className="testing-empty-hint">
                {listItems.length === 0
                  ? "Run a behavioral test or load sample data to view results."
                  : "Select a test run from the list."}
              </p>
            </div>
          ) : (
            <>
              {selectedPersistence ? (
                <div className="glass-card" style={{ padding: 12, fontSize: 13, color: "var(--text-muted)" }}>
                  <strong style={{ color: "#e5e7eb" }}>
                    {selectedPersistence === "session"
                      ? "Current session run"
                      : selectedPersistence === "stable_saved"
                        ? "Stable saved run"
                        : "Saved history run"}
                  </strong>
                  {" — "}
                  {persistenceHintForState(selectedPersistence)}
                </div>
              ) : null}
              <TestingSummaryBar run={runView} />
              <TestingLayeredScoringPanel run={runView} />
              {selectedRun.target_type === "project" && selectedRun.project_summary?.file_summaries.length ? (
                <div className="glass-card" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                  <div className="panel-label">Project files</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                    <button
                      type="button"
                      className={`action-button ${selectedFilePath === null ? "primary" : "secondary"}`}
                      onClick={() => setSelectedFilePath(null)}
                    >
                      All files (aggregate)
                    </button>
                    {selectedRun.project_summary.file_summaries.map((f) => {
                      const fileRow = selectedRun.file_results?.find((r) => r.path === f.path);
                      const fileStatus = fileRow?.status ?? f.status;
                      return (
                      <button
                        key={f.path}
                        type="button"
                        className={`action-button ${selectedFilePath === f.path ? "primary" : "secondary"}`}
                        onClick={() => setSelectedFilePath(f.path)}
                        title={f.status === "skipped" ? f.reason : undefined}
                      >
                        {f.program_name}
                        {fileStatus !== "passed" ? ` (${fileStatus})` : ""}
                      </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}
              <TestingScenarioPanel inputSet={displayRun.input_set} />
              <TestingDiffPanel
                cobolOutput={runView.cobol_output}
                javaOutput={runView.java_output}
                diffSummary={runView.diff_summary}
                executionMode={runView.execution_mode}
                failureReason={runView.failure_reason}
                fallbackMode={runView.fallback_mode}
              />
              <div className="testing-two-col">
                <TestingFailedTestsPanel failedTests={runView.failed_tests} />
                <TestingFailurePanel
                  run={runView}
                  derivedScope={derivedRetryScope}
                  scopeLoading={scopeLoading}
                  retryLoading={retryLoading}
                  onRetryScope={() => void handleRetryScope()}
                  runValidationLoop={runValidationLoop}
                  onToggleValidationLoop={setRunValidationLoop}
                />
              </div>
              {retryError ? (
                <p className="testing-panel-hint" style={{ color: "var(--error)", padding: "0 4px" }}>
                  {retryError}
                </p>
              ) : null}
              {retryResult ? (
                <TestingRetryOutcomePanel
                  result={retryResult}
                  onSaveToHistory={
                    retryResult.ready_to_save && retryResult.test_result ? handleSaveStableRun : undefined
                  }
                  saving={saveStableLoading}
                />
              ) : null}
              {canGenerateBrTests ? (
                <TestingBusinessRulesPanel
                  result={brTestResult}
                  loading={brTestLoading}
                  error={brTestError}
                  canGenerate={canGenerateBrTests}
                  onGenerate={() => void handleGenerateBrTests()}
                />
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
