"use client";

import React from 'react';

interface JsonViewerProps {
  data: unknown;
  title?: string;
}

export default function JsonViewer({ data, title }: JsonViewerProps) {
  return (
    <div className="json-container">
      {title && <div className="json-title">{title}</div>}
      <pre className="json-content">
        <code>{JSON.stringify(data, null, 2)}</code>
      </pre>

      <style jsx>{`
        .json-container {
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid var(--border);
          border-radius: 8px;
          overflow: hidden;
          font-family: var(--font-mono);
          height: 100%;
          display: flex;
          flex-direction: column;
        }

        .json-title {
          padding: 8px 16px;
          background: rgba(255, 255, 255, 0.05);
          border-bottom: 1px solid var(--border);
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-muted);
          font-weight: 600;
        }

        .json-content {
          padding: 16px;
          margin: 0;
          overflow: auto;
          flex: 1;
          font-size: 13px;
          line-height: 1.5;
          color: #a5d6ff; /* Soft blue for JSON */
        }

        code {
          white-space: pre-wrap;
          word-break: break-all;
        }
      `}</style>
    </div>
  );
}
