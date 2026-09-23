/** Mirrors the backend's profile schemas (app/modules/profiles/schemas.py). */

export type Availability = "available" | "limited" | "unavailable";

export type VerificationStatus = "unverified" | "pending" | "verified" | "rejected";

export interface ProfileLink {
  label: string;
  url: string;
}

export interface StudentProfile {
  profile_type: "student";
  department_id: string | null;
  department_locked: boolean;
  program: string;
  year: number;
  bio: string | null;
  interests: string | null;
  is_discoverable: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResearcherProfile {
  profile_type: "researcher";
  department_id: string | null;
  department_locked: boolean;
  designation: string;
  bio: string | null;
  availability: Availability;
  links: ProfileLink[] | null;
  verification_status: VerificationStatus;
  verified_by: string | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export type Profile = StudentProfile | ResearcherProfile;

export interface StudentProfileUpdate {
  program: string;
  department_id?: string | null;
  year: number;
  bio?: string | null;
  interests?: string | null;
  is_discoverable: boolean;
}

export interface ResearcherProfileUpdate {
  designation: string;
  department_id?: string | null;
  bio?: string | null;
  availability: Availability;
  links?: ProfileLink[] | null;
}

export interface SkillEntry {
  skill_id: string;
  proficiency: number;
}

export interface ResearchAreaEntry {
  research_area_id: string;
  is_expertise: boolean;
}
