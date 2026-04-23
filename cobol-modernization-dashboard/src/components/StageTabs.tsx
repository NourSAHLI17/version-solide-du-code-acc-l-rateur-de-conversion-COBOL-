"use client";

interface StageTab {
  id: string;
  label: string;
  stage: "parser" | "analysis" | "java" | "tests";
}

interface StageTabsProps {
  tabs: StageTab[];
  activeTab: string;
  onChange: (tab: string) => void;
}

export default function StageTabs({ tabs, activeTab, onChange }: StageTabsProps) {
  return (
    <div className="stage-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          className={`stage-tab ${activeTab === tab.id ? "active" : ""}`}
          data-stage={tab.stage}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
