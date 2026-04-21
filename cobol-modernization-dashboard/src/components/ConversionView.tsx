"use client";

import React from 'react';
import JsonViewer from './JsonViewer';

interface ConversionViewProps {
  analysisData: unknown;
  javaSource: string;
  onNext: () => void;
}

export default function ConversionView({ analysisData, javaSource, onNext }: ConversionViewProps) {
  return (
    <div className="glass-card animate-fade-in conversion-grid">
      <div className="view-column">
        <label>Semantic Context</label>
        <JsonViewer data={analysisData} title="analysis.json" />
      </div>

      <div className="connector">
        <div className="agent-orb">AI</div>
        <div className="label">Conversion Agent</div>
      </div>

      <div className="view-column">
        <label>Generated Java</label>
        <div className="code-container">
          <pre><code>{javaSource}</code></pre>
        </div>
      </div>

      <div className="actions-footer">
        <button className="next-btn" onClick={onNext}>
          Validate Equivalence
        </button>
      </div>

      <style jsx>{`
        .conversion-grid {
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

        .code-container {
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 16px;
          overflow: auto;
          flex: 1;
          font-family: var(--font-mono);
          font-size: 13px;
          line-height: 1.5;
          color: #d1d5db;
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
          background: linear-gradient(135deg, var(--secondary), var(--primary));
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 800;
          color: white;
          box-shadow: 0 0 20px rgba(236, 72, 153, 0.4);
          animation: float 3s infinite ease-in-out;
        }

        @keyframes float {
          0% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
          100% { transform: translateY(0); }
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
