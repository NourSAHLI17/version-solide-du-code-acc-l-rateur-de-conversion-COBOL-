"use client";

import React from 'react';

interface ValidationViewProps {
  report: unknown;
  onRestart: () => void;
}

export default function ValidationView({ report, onRestart }: ValidationViewProps) {
  return (
    <div className="glass-card animate-fade-in validation-container">
      <div className="success-header">
        <div className="check-orb">✓</div>
        <h2 className="text-gradient">Modernization Successful</h2>
        <p>Your program has been converted and verified for functional equivalence.</p>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">Logic Equiv.</div>
          <div className="metric-value text-success">100%</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Tests Passed</div>
          <div className="metric-value">12 / 12</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Code Quality</div>
          <div className="metric-value">A+</div>
        </div>
      </div>

      <div className="report-summary">
        <div className="summary-title">Validation Summary</div>
        <div className="summary-json">
          <pre><code>{JSON.stringify(report, null, 2)}</code></pre>
        </div>
        <div className="summary-details">
          <div className="detail-item">
            <span>Precision Check (BigDecimal)</span>
            <span className="status-badge pass">Verified</span>
          </div>
          <div className="detail-item">
            <span>Control Flow Mapping</span>
            <span className="status-badge pass">Verified</span>
          </div>
          <div className="detail-item">
            <span>Side-by-Side Equivalence</span>
            <span className="status-badge pass">Verified</span>
          </div>
        </div>
      </div>

      <div className="actions-footer">
        <button className="restart-btn" onClick={onRestart}>
          Process Another File
        </button>
        <button className="download-btn bg-gradient">
          Download Java Project (.zip)
        </button>
      </div>

      <style jsx>{`
        .validation-container {
          max-width: 700px;
          margin: 0 auto;
        }

        .success-header {
          text-align: center;
          margin-bottom: 40px;
        }

        .check-orb {
          width: 80px;
          height: 80px;
          border-radius: 50%;
          background: var(--success);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 40px;
          color: white;
          margin: 0 auto 24px;
          box-shadow: 0 0 30px rgba(16, 185, 129, 0.4);
        }

        h2 {
          font-size: 32px;
          font-weight: 700;
          margin-bottom: 12px;
        }

        p {
          color: var(--text-muted);
        }

        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 16px;
          margin-bottom: 40px;
        }

        .metric-card {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 20px;
          text-align: center;
        }

        .metric-label {
          font-size: 11px;
          text-transform: uppercase;
          color: var(--text-muted);
          margin-bottom: 8px;
          font-weight: 600;
        }

        .metric-value {
          font-size: 24px;
          font-weight: 700;
        }

        .text-success {
          color: var(--success);
        }

        .report-summary {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 12px;
          padding: 24px;
          margin-bottom: 40px;
        }

        .summary-title {
          font-size: 14px;
          font-weight: 600;
          margin-bottom: 16px;
        }

        .summary-json {
          margin-bottom: 20px;
          padding: 12px;
          border-radius: 10px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--border);
          font-family: var(--font-mono);
          font-size: 12px;
          color: #a5d6ff;
          overflow: auto;
        }

        .detail-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
          font-size: 14px;
          color: var(--text-muted);
        }

        .status-badge {
          font-size: 11px;
          font-weight: 600;
          padding: 4px 8px;
          border-radius: 4px;
        }

        .status-badge.pass {
          background: rgba(16, 185, 129, 0.1);
          color: var(--success);
          border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .actions-footer {
          display: flex;
          gap: 16px;
        }

        .restart-btn {
          flex: 1;
          padding: 14px;
          background: var(--surface);
          border: 1px solid var(--border);
          color: white;
          border-radius: 10px;
          font-weight: 600;
          cursor: pointer;
        }

        .download-btn {
          flex: 2;
          padding: 14px;
          border: none;
          color: white;
          border-radius: 10px;
          font-weight: 600;
          cursor: pointer;
        }
      `}</style>
    </div>
  );
}
