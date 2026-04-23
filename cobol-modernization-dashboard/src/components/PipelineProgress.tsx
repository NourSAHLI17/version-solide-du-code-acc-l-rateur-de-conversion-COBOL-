"use client";

import type { PipelineMode } from "@/lib/pipelineModes";
import { STAGES_FOR_MODE } from "@/lib/pipelineModes";

interface PipelineProgressProps {
  currentStage: string | null;
  mode: PipelineMode;
}

export default function PipelineProgress({ currentStage, mode }: PipelineProgressProps) {
  if (!currentStage) {
    return null;
  }

  const stages = STAGES_FOR_MODE[mode] ?? STAGES_FOR_MODE.full;
  const activeIndex = Math.max(0, stages.findIndex((stage) => stage.toLowerCase() === currentStage.toLowerCase()));

  return (
    <div className="pipeline-progress">
      <div className="progress-spinner" />
      <div className="progress-stages">
        {stages.map((stage, index) => (
          <span key={stage} className={index < activeIndex ? "done" : index === activeIndex ? "active" : ""}>
            {stage}
          </span>
        ))}
      </div>
    </div>
  );
}
