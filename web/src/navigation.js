import {
  IconBell,
  IconChart,
  IconDoc,
  IconHistory,
  IconTarget,
  IconWallet,
} from "./icons.jsx";

export const GROUPS = [
  { id: "research", label: "Araştırma", icon: IconChart, tabs: ["overview", "findings"] },
  { id: "analysis", label: "Analiz", icon: IconTarget, tabs: ["accuracy", "compare"] },
  { id: "tracking", label: "Takip", icon: IconWallet, tabs: ["watchlist", "portfolio", "carry"] },
  { id: "output", label: "Üretim", icon: IconDoc, tabs: ["report", "prompt"] },
  { id: "archive", label: "Arşiv", icon: IconHistory, tabs: ["rag", "history"] },
];

export const TAB_LABELS = {
  overview: "Genel Bakış",
  findings: "Bulgular",
  accuracy: "İsabet",
  compare: "Karşılaştır",
  watchlist: "Takip Listesi",
  portfolio: "Portföy",
  carry: "Fonlama Carry",
  report: "Rapor",
  prompt: "Prompt Çıktısı",
  rag: "Kaynak Arama",
  history: "Rapor Arşivi",
};

export function groupOfTab(tab) {
  return GROUPS.find((group) => group.tabs.includes(tab)) || GROUPS[0];
}

export { IconBell };
