import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import type * as ApiOrgModule from "@/features/directory/api-org";

import { ProfileForm } from "./ProfileForm";

// The department picker fetches the department list; the list itself isn't
// what these tests are about, so it stays empty.
vi.mock("@/features/directory/api-org", async (importOriginal) => ({
  // The real departmentLabel: how a department reads in the list is part of
  // what these tests are checking, not something to stub out.
  ...(await importOriginal<typeof ApiOrgModule>()),
  fetchDepartments: () =>
    Promise.resolve([
      { id: "d-elec", name: "Electrical Engineering", school_id: "s1", school_name: "Engineering" },
      { id: "d-cs", name: "Computer Science", school_id: "s1", school_name: "Engineering" },
    ]),
}));

function renderForm(element: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{element}</QueryClientProvider>);
}

describe("ProfileForm", () => {
  it("renders student fields for a student and validates them", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(
      <ProfileForm role="student" profile={null} submitLabel="Save" onSubmit={onSubmit} />,
    );

    expect(screen.getByLabelText(/programme/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/designation/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/programme is required/i)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a valid student profile", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(
      <ProfileForm role="student" profile={null} submitLabel="Save" onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText(/programme/i), "B.Tech CSE");
    await user.clear(screen.getByLabelText(/year of study/i));
    await user.type(screen.getByLabelText(/year of study/i), "2");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSubmit).toHaveBeenCalledWith({
      program: "B.Tech CSE",
      year: 2,
      bio: null,
      interests: null,
      is_discoverable: false,
      department_id: null,
    });
  });

  it("renders researcher fields for faculty and rejects a malformed link", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(
      <ProfileForm role="faculty" profile={null} submitLabel="Save" onSubmit={onSubmit} />,
    );

    expect(screen.getByLabelText(/designation/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/programme/i)).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/designation/i), "Assistant Professor");
    await user.type(screen.getByLabelText(/profile link/i), "not-a-url");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/enter a full url/i)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a valid researcher profile with a link", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(
      <ProfileForm role="faculty" profile={null} submitLabel="Save" onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText(/designation/i), "Professor");
    await user.type(screen.getByLabelText(/profile link/i), "https://example.com/me");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSubmit).toHaveBeenCalledWith({
      designation: "Professor",
      bio: null,
      availability: "available",
      links: [{ label: "Profile", url: "https://example.com/me" }],
      department_id: null,
    });
  });
});

describe("the department picker", () => {
  it("preselects the department the student already has", async () => {
    // The list arrives from its own query, so on the first render this select
    // held only "Not set" — and a <select> whose value is not among its
    // options shows the FIRST one. A student in Electrical Engineering was
    // shown "Not set" on their own profile, and invited to "correct" it by
    // picking another department, which would have moved them to a different
    // coordinator.
    renderForm(
      <ProfileForm
        role="student"
        profile={{
          profile_type: "student",
          department_id: "d-elec",
          department_locked: false,
          program: "B.Tech Electronics",
          year: 3,
          bio: null,
          interests: null,
          is_discoverable: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }}
        submitLabel="Save"
        onSubmit={vi.fn()}
      />,
    );

    // Wait for the options themselves: the field shows a disabled
    // placeholder until they arrive, which is precisely what stops the value
    // being applied against a half-built list.
    await screen.findByRole("option", { name: "Electrical Engineering" });
    expect(screen.getByLabelText("Department", { exact: true })).toHaveValue("d-elec");
  });
});
