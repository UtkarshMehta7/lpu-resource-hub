import type { OpportunityCard } from "@/features/opportunities/api";
import { TYPE_LABEL } from "@/features/opportunities/labels";
import type { ProjectCard } from "@/features/projects/api";
import { STATUS_LABEL } from "@/features/projects/labels";

import type { RecommendedItem } from "./api";

export interface CardSummary {
  title: string;
  subtitle: string;
  to: string;
}

function isOpportunity(item: RecommendedItem): item is OpportunityCard {
  return "opportunity_type" in item;
}

function isProject(item: RecommendedItem): item is ProjectCard {
  return "owner_name" in item;
}

/** One shape per card type, so the page can render any recommendation. */
export function describe(item: RecommendedItem): CardSummary {
  if (isOpportunity(item)) {
    return {
      title: item.title,
      subtitle: `${TYPE_LABEL[item.opportunity_type]} · deadline ${item.deadline} · ${item.accepted_count}/${item.positions} filled`,
      to: `/opportunities/${item.id}`,
    };
  }
  if (isProject(item)) {
    return {
      title: item.title,
      subtitle: `${STATUS_LABEL[item.status]} · led by ${item.owner_name}`,
      to: `/projects/${item.id}`,
    };
  }
  if ("designation" in item) {
    return {
      title: item.full_name,
      subtitle: item.designation,
      to: `/researchers/${item.user_id}`,
    };
  }
  // Students have no public detail page; they're contacted from the
  // discovery list.
  return {
    title: item.full_name,
    subtitle: `${item.program} · year ${item.year}`,
    to: "/students",
  };
}
