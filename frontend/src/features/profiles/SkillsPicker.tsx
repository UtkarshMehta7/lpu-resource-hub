import { useCallback } from "react";

import { TagPicker, type TagOption } from "@/components/ui/TagPicker";
import { searchSkills } from "@/features/taxonomy/api";

export interface SelectedSkill {
  id: string;
  name: string;
  proficiency: number;
}

interface SkillsPickerProps {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
}

export function SkillsPicker({ selected, onChange }: SkillsPickerProps) {
  const search = useCallback(
    async (query: string): Promise<TagOption[]> =>
      (await searchSkills(query || undefined)).map((skill) => ({
        id: skill.id,
        name: skill.name,
      })),
    [],
  );

  return (
    <TagPicker
      label="Skills"
      description="At least 3 skills are needed before recommendations can be generated."
      search={search}
      selected={selected.map(({ id, name }) => ({ id, name }))}
      onAdd={(option) => onChange([...selected, { ...option, proficiency: 3 }])}
      onRemove={(id) => onChange(selected.filter((skill) => skill.id !== id))}
      renderSelectedExtra={(option) => {
        const current = selected.find((skill) => skill.id === option.id);
        return (
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            Proficiency
            <select
              aria-label={`Proficiency for ${option.name}`}
              value={current?.proficiency ?? 3}
              onChange={(event) =>
                onChange(
                  selected.map((skill) =>
                    skill.id === option.id
                      ? { ...skill, proficiency: Number(event.target.value) }
                      : skill,
                  ),
                )
              }
              className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
            >
              {[1, 2, 3, 4, 5].map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </label>
        );
      }}
    />
  );
}
