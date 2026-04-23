"use client";

import type { PipelineMode, PipelineModeOption } from "@/lib/pipelineModes";

interface PipelineModeSelectorProps {
  value: PipelineMode;
  onChange: (mode: PipelineMode) => void;
  modes: PipelineModeOption[];
  compact?: boolean;
}

export default function PipelineModeSelector({ value, onChange, modes, compact = false }: PipelineModeSelectorProps) {
  const selected = modes.find((mode) => mode.value === value) ?? modes[0];

  return (
    <div className={`mode-selector ${compact ? "compact" : ""}`}>
      <label className="mode-select-label" htmlFor="pipeline-mode">
        Pipeline Mode
      </label>
      <div className="select-shell" data-tone={selected.color}>
        <select
          id="pipeline-mode"
          value={value}
          onChange={(event) => onChange(event.target.value as PipelineMode)}
          className="mode-select"
        >
          {modes.map((mode) => (
            <option key={mode.value} value={mode.value}>
              {mode.label}
            </option>
          ))}
        </select>
      </div>

      {!compact && (
        <div className="mode-grid" role="list">
          {modes.map((mode) => (
            <button
              key={mode.value}
              type="button"
              className={`mode-card ${value === mode.value ? "active" : ""}`}
              data-tone={mode.color}
              onClick={() => onChange(mode.value)}
            >
              <span className="mode-dot" />
              <span>
                <strong>{mode.label}</strong>
                <small>{mode.description}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
