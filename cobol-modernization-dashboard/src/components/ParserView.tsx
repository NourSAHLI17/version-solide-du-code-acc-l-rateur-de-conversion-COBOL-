"use client";

import React from 'react';
import JsonViewer from './JsonViewer';

interface ParserViewProps {
  cobolSource: string;
  astData: unknown;
  onNext: () => void;
}

export default function ParserView({ cobolSource, astData, onNext }: ParserViewProps) {
  return (
    <div className="glass-card animate-fade-in parser-grid">
      <div className="view-column">
        <label>COBOL Source</label>
        <div className="code-container">
          <pre><code>{cobolSource}</code></pre>
        </div>
      </div>

      <div className="connector">
        <div className="arrow">→</div>
        <div className="label">Determinisic Parser</div>
      </div>

      <div className="view-column">
        <label>AST Structure</label>
        <JsonViewer data={astData} title="ast.json" />
      </div>

      <div className="actions-footer">
        <button className="next-btn" onClick={onNext}>
          Analyze Semantics
        </button>
      </div>

      <style jsx>{`
        .parser-grid {
          display: grid;
          grid-template-columns: 1fr 100px 1fr;
          gap: 20px;
          height: 600px;
          position: relative;
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
          color: var(--text-muted);
        }

        .connector {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
        }

        .arrow {
          font-size: 24px;
          color: var(--primary);
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
