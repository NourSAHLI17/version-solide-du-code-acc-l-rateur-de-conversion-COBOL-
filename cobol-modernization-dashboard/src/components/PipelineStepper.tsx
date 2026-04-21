"use client";

import React from 'react';

export type Stage = 'upload' | 'parsing' | 'analysis' | 'conversion' | 'validation';

interface PipelineStepperProps {
  currentStage: Stage;
  stages: { id: Stage; label: string }[];
}

export default function PipelineStepper({ currentStage, stages }: PipelineStepperProps) {
  const currentIndex = stages.findIndex(s => s.id === currentStage);

  return (
    <div className="stepper-container">
      {stages.map((stage, index) => {
        const isActive = index === currentIndex;
        const isCompleted = index < currentIndex;
        
        return (
          <React.Fragment key={stage.id}>
            <div className={`step ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}>
              <div className="step-icon">
                {isCompleted ? '✓' : index + 1}
              </div>
              <div className="step-label">{stage.label}</div>
            </div>
            {index < stages.length - 1 && (
              <div className={`step-connector ${isCompleted ? 'completed' : ''}`} />
            )}
          </React.Fragment>
        );
      })}

      <style jsx>{`
        .stepper-container {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          max-width: 800px;
          margin: 0 auto 48px;
          padding: 0 20px;
        }

        .step {
          display: flex;
          flex-direction: column;
          align-items: center;
          position: relative;
          z-index: 1;
        }

        .step-icon {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: var(--surface);
          border: 2px solid var(--border);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          font-size: 14px;
          color: var(--text-muted);
          transition: all 0.3s ease;
        }

        .step.active .step-icon {
          background: var(--primary);
          border-color: var(--primary);
          color: white;
          box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
        }

        .step.completed .step-icon {
          background: var(--success);
          border-color: var(--success);
          color: white;
        }

        .step-label {
          margin-top: 12px;
          font-size: 13px;
          font-weight: 500;
          color: var(--text-muted);
          white-space: nowrap;
          transition: all 0.3s ease;
        }

        .step.active .step-label {
          color: var(--foreground);
        }

        .step-connector {
          flex: 1;
          height: 2px;
          background: var(--border);
          margin: -24px 12px 0;
          position: relative;
          transition: all 0.5s ease;
        }

        .step-connector.completed {
          background: var(--success);
        }
      `}</style>
    </div>
  );
}
