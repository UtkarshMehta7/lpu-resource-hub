import { useCallback } from "react";

import { TagPicker, type TagOption } from "@/components/ui/TagPicker";
import { searchResearchAreas } from "@/features/taxonomy/api";

export interface SelectedResearchArea {
  id: string;
  name: string;
  isExpertise: boolean;
}

interface ResearchAreasPickerProps {
  selected: SelectedResearchArea[];
  onChange: (next: SelectedResearchArea[]) => void;
}

export function ResearchAreasPicker({ selected, onChange }: ResearchAreasPickerProps) {
  const search = useCallback(
    async (query: string): Promise<TagOption[]> =>
      (await searchResearchAreas(query || undefined)).map((area) => ({
        id: area.id,
        name: area.name,
      })),
    [],
  );

  return (
    <TagPicker
      label="Research areas"
      description="At least 3 areas are needed before recommendations can be generated. Aliases work too — try “ML”."
      search={search}
      selected={selected.map(({ id, name }) => ({ id, name }))}
      onAdd={(option) => onChange([...selected, { ...option, isExpertise: false }])}
      onRemove={(id) => onChange(selected.filter((area) => area.id !== id))}
      renderSelectedExtra={(option) => {
        const current = selected.find((area) => area.id === option.id);
        return (
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            <input
              type="checkbox"
              aria-label={`Mark ${option.name} as expertise`}
              checked={current?.isExpertise ?? false}
              onChange={(event) =>
                onChange(
                  selected.map((area) =>
                    area.id === option.id ? { ...area, isExpertise: event.target.checked } : area,
                  ),
                )
              }
            />
            Expertise
          </label>
        );
      }}
    />
  );
}
