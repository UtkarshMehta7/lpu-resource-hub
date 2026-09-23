import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { ProfileForm } from "./ProfileForm";

// The department picker fetches the department list; the list itself isn't
// what these tests are about, so it stays empty.
vi.mock("@/features/directory/api-org", () => ({
  fetchDepartments: () => Promise.resolve([]),
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
