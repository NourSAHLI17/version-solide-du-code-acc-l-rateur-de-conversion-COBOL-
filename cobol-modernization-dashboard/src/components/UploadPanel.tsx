"use client";

import React from 'react';

interface UploadPanelProps {
  onStart: () => void;
}

export default function UploadPanel({ onStart }: UploadPanelProps) {
  return (
    <div className="glass-card animate-fade-in">
      <div className="upload-header">
        <h2 className="text-gradient">Ready to Modernize?</h2>
        <p>Drop your COBOL artifacts here to start the AI-powered transformation pipeline.</p>
      </div>

      <div className="drop-zone">
        <div className="drop-icon">↑</div>
        <p>Drag and drop <span>.cbl</span>, <span>.cpy</span>, or <span>.jcl</span> files</p>
        <button className="browse-btn">Browse Files</button>
      </div>

      <div className="file-requirements">
        <div className="req-item">
          <span className="dot" />
          <span>COBOL Source (.cbl)</span>
        </div>
        <div className="req-item">
          <span className="dot" />
          <span>Copybooks (.cpy)</span>
        </div>
        <div className="req-item">
          <span className="dot" />
          <span>JCL Definitions (.jcl)</span>
        </div>
      </div>

      <button className="start-btn bg-gradient" onClick={onStart}>
        Execute Pipeline
      </button>

      <style jsx>{`
        .upload-header {
          text-align: center;
          margin-bottom: 32px;
        }

        h2 {
          font-size: 28px;
          font-weight: 700;
          margin-bottom: 12px;
        }

        p {
          color: var(--text-muted);
          font-size: 15px;
        }

        .drop-zone {
          border: 2px dashed var(--border);
          border-radius: 12px;
          padding: 48px;
          text-align: center;
          cursor: pointer;
          transition: all 0.3s ease;
          background: rgba(255, 255, 255, 0.01);
          margin-bottom: 32px;
        }

        .drop-zone:hover {
          border-color: var(--primary);
          background: rgba(99, 102, 241, 0.05);
        }

        .drop-icon {
          font-size: 32px;
          margin-bottom: 16px;
          color: var(--primary);
        }

        .drop-zone p span {
          color: var(--primary);
          font-weight: 600;
        }

        .browse-btn {
          margin-top: 20px;
          background: var(--surface);
          border: 1px solid var(--border);
          color: white;
          padding: 8px 16px;
          border-radius: 6px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
        }

        .file-requirements {
          display: flex;
          justify-content: center;
          gap: 24px;
          margin-bottom: 40px;
        }

        .req-item {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: var(--text-muted);
        }

        .dot {
          width: 6px;
          height: 6px;
          background: var(--primary);
          border-radius: 50%;
        }

        .start-btn {
          width: 100%;
          padding: 16px;
          border: none;
          border-radius: 12px;
          color: white;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: transform 0.2s ease, opacity 0.2s ease;
        }

        .start-btn:hover {
          transform: translateY(-2px);
          opacity: 0.9;
        }

        .start-btn:active {
          transform: translateY(0);
        }
      `}</style>
    </div>
  );
}
