"use client";

import type { ToolchainGuidance } from "@/lib/testingAgentTypes";

export default function TestingToolchainBanner({
  guidance,
  loading,
  showSetupDetails,
  onRunTest,
  onEnableFallback,
  onToggleSetup,
  onScrollToResults,
}: {
  guidance: ToolchainGuidance | null;
  loading?: boolean;
  showSetupDetails?: boolean;
  onRunTest?: () => void;
  onEnableFallback?: () => void;
  onToggleSetup?: () => void;
  onScrollToResults?: () => void;
}) {
  if (loading && !guidance) {
    return (
      <div className="testing-toolchain-banner testing-toolchain-banner--neutral glass-card" role="status">
        <p className="testing-toolchain-banner__title">Checking execution environment…</p>
        <p className="testing-toolchain-banner__subtext">Probing COBOL and Java toolchains on the API host.</p>
      </div>
    );
  }

  if (!guidance) return null;

  const tone = guidance.banner_tone;
  const action = guidance.recommended_action;

  const handleAction = () => {
    if (action === "run_live" || action === "use_snapshot") {
      onRunTest?.();
      return;
    }
    if (action === "install_toolchain") {
      onToggleSetup?.();
      return;
    }
    if (action === "review_mixed") {
      onScrollToResults?.();
    }
  };

  const showActionButton =
    Boolean(guidance.action_label) &&
    (action === "run_live" ||
      action === "use_snapshot" ||
      action === "install_toolchain" ||
      action === "review_mixed");

  const showEnableFallback =
    action === "install_toolchain" && !guidance.fallback_mode && onEnableFallback;

  return (
    <div className={`testing-toolchain-banner testing-toolchain-banner--${tone} glass-card`} role="status">
      <div className="testing-toolchain-banner__body">
        <p className="testing-toolchain-banner__title">{guidance.banner_title}</p>
        <p className="testing-toolchain-banner__subtext">{guidance.banner_subtext}</p>
        {guidance.missing_tools.length > 0 && tone === "warning" ? (
          <p className="testing-toolchain-banner__meta">
            Missing on API host: {guidance.missing_tools.join(", ")}
          </p>
        ) : null}
        {showSetupDetails ? (
          <div id="testing-toolchain-setup" className="testing-toolchain-banner__setup">
            <p className="testing-toolchain-banner__setup-title">Enable live behavioral testing</p>
            <ol>
              <li>Install GnuCOBOL so <code>cobc</code> is on the API server PATH.</li>
              <li>Install a JDK so <code>javac</code> and <code>java</code> are on PATH.</li>
              <li>Restart the modernization API service after installation.</li>
              <li>
                Alternatively, enable <strong>Snapshot fallback</strong> below to compare stored stdout
                without live execution.
              </li>
            </ol>
            <p className="testing-toolchain-banner__setup-note">
              If you cannot change the server, contact your platform administrator.
            </p>
          </div>
        ) : null}
      </div>
      <div className="testing-toolchain-banner__actions">
        {showActionButton ? (
          <button type="button" className="action-button primary" onClick={handleAction}>
            {guidance.action_label}
          </button>
        ) : null}
        {showEnableFallback ? (
          <button type="button" className="action-button secondary" onClick={onEnableFallback}>
            Enable snapshot fallback
          </button>
        ) : null}
      </div>
    </div>
  );
}
