"use client";

import { useState } from "react";

import CopyButton from "@/components/CopyButton";
import DownloadButton from "@/components/DownloadButton";

export default function StageOutputPanel({
  title,
  children,
  copyText,
  download,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  copyText?: string;
  download?: { filename: string; content: string; mime: string; label?: string };
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="stage-output-panel">
      <button type="button" className="stage-output-panel-header" onClick={() => setOpen((o) => !o)}>
        <span>{title}</span>
        <span>{open ? "▼" : "▶"}</span>
      </button>
      {open ? (
        <div className="stage-output-panel-body">
          {children}
          {(copyText || download) && (
            <div className="stage-output-actions">
              {copyText ? <CopyButton text={copyText} /> : null}
              {download ? (
                <DownloadButton
                  filename={download.filename}
                  content={download.content}
                  mime={download.mime}
                  label={download.label}
                  disabled={!download.content}
                />
              ) : null}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

