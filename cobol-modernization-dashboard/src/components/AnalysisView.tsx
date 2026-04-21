"use client";

import React from 'react';
import JsonViewer from './JsonViewer';

interface AnalysisViewProps {
  astData: unknown;
  analysisData: unknown;
  onNext: () => void;
}

export default function AnalysisView({ astData, analysisData, onNext }: AnalysisViewProps) {
  return (
    <div className="glass-card animate-fade-in analysis-grid">
      <div className="view-column">
        <label>Parser Artifacts</label>
        <JsonViewer data={astData} title="ast.json" />
      </div>

      <div className="connector">
        <div className="agent-orb">AI</div>
        <div className="label">Analysis Agent</div>
      </div>

      <div className="view-column">
        <label>Semantic Understanding</label>
        <JsonViewer data={analysisData} title="analysis.json" />
      </div>

      <div className="actions-footer">
        <button className="next-btn" onClick={onNext}>
          Generate Java Code
        </button>
      </div>

      <style jsx>{`
        .analysis-grid {
          display: grid;
          grid-template-columns: 1fr 100px 1fr;
          gap: 20px;
          height: 600px;
        }

        .view-column {
          display: flex;
          flex-direction: column;
          height: 100%;
          overflow: hidden;
        }

        label {
          font-size: 11px;
          text-transform: uppercase;
          color: var(--text-muted);
          margin-bottom: 8px;
          font-weight: 600;
        }

        .connector {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
        }

        .agent-orb {
          width: 50px;
          height: 50px;
          border-radius: 50%;
          background: linear-gradient(135deg, var(--primary), var(--secondary));
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 800;
          color: white;
          box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
          animation: pulse 2s infinite ease-in-out;
        }

        @keyframes pulse {
          0% { transform: scale(1); box-shadow: 0 0 20px rgba(99, 102, 241, 0.4); }
          50% { transform: scale(1.05); box-shadow: 0 0 30px rgba(236, 72, 153, 0.5); }
          100% { transform: scale(1); box-shadow: 0 0 20px rgba(99, 102, 241, 0.4); }
        }

        .label {
          font-size: 10px;
          text-align: center;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.1em;
        }

        .actions-footer {
          grid-column: 1 / -1;
          margin-top: 20px;
          display: flex;
          justify-content: flex-end;
        }

        .next-btn {
          background: var(--primary);
          color: white;
          border: none;
          padding: 10px 24px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.2s;
        }

        .next-btn:hover {
          background: var(--primary-hover);
        }
      `}</style>
    </div>
  );
}
