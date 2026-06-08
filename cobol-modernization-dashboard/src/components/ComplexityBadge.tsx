"use client";

import { filterComplexityDriversForTooltip } from "@/lib/conversionScore";

export interface ComplexityBadgeProps {
  tier: string;
  ibmRating?: string;
  drivers?: string[];
}

const TIER_STYLES: Record<string, string> = {
  Standard: "complexity-badge complexity-badge-standard",
  Complex: "complexity-badge complexity-badge-complex",
  Enterprise: "complexity-badge complexity-badge-enterprise",
};

export default function ComplexityBadge({ tier, ibmRating, drivers }: ComplexityBadgeProps) {
  const styleClass = TIER_STYLES[tier] || TIER_STYLES.Complex;
  const tooltipDrivers = filterComplexityDriversForTooltip(drivers ?? []);

  return (
    <span className="complexity-badge-wrap">
      <span className={styleClass}>{tier}</span>
      <span className="complexity-badge-tooltip" role="tooltip">
        <p className="complexity-badge-tooltip-title">{tier} Complexity</p>
        {ibmRating ? (
          <p className="complexity-badge-tooltip-sub">IBM equivalent: {ibmRating}</p>
        ) : null}
        {tooltipDrivers.length > 0 ? (
          <ul className="complexity-badge-tooltip-list">
            {tooltipDrivers.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        ) : null}
      </span>
    </span>
  );
}
