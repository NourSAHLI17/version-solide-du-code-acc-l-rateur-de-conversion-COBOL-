"use client";

import StatusBadge from "@/components/StatusBadge";
import {
  reliabilityBadgeFromScore,
  type ReliabilityBadgeInfo,
} from "@/lib/reliabilityBadge";

export default function ReliabilityScoreBadge({
  score,
  badge,
  forceSave,
  compact = true,
}: {
  score?: number | null;
  badge?: ReliabilityBadgeInfo;
  forceSave?: boolean;
  compact?: boolean;
}) {
  const info = badge ?? reliabilityBadgeFromScore(score);
  return (
    <span className="reliability-badge-wrap">
      <StatusBadge label={info.displayText} tone={info.tone} compact={compact} />
      {forceSave ? (
        <span className="reliability-badge-manual" title="Saved manually below auto-save threshold">
          Manually Saved
        </span>
      ) : null}
    </span>
  );
}
