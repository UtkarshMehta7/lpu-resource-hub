import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AUTHOR_LINKEDIN, AUTHOR_NAME } from "@/components/layout/Brand";

import { AppLayout } from "./AppLayout";

// The header pulls in auth, routing and queries; the footer is what is under
// test, so the header is stubbed out rather than stood up.
vi.mock("@/components/layout/Header", () => ({ Header: () => <header /> }));

function renderLayout() {
  render(
    <MemoryRouter>
      <AppLayout />
    </MemoryRouter>,
  );
}

describe("the footer", () => {
  it("credits the author on every page, as a real link", () => {
    renderLayout();

    const link = screen.getByRole("link", { name: new RegExp(`Developed by ${AUTHOR_NAME}`, "i") });
    expect(link).toHaveAttribute("href", AUTHOR_LINKEDIN);
  });

  it("opens the profile safely in a new tab", () => {
    // target=_blank without noopener hands the new tab a handle on this one.
    renderLayout();

    const link = screen.getByRole("link", { name: new RegExp(AUTHOR_NAME, "i") });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
    expect(link.getAttribute("rel")).toMatch(/noreferrer/);
  });

  it("keeps the prototype disclaimer and the administration entrance", () => {
    // The credit sits beside these, and must not have displaced either: the
    // disclaimer is the honest part, and the admin link is how an
    // administrator finds their own sign-in without knowing the URL.
    renderLayout();

    expect(screen.getByText(/Not an official LPU system/i)).toBeInTheDocument();
    expect(screen.getByText(/fictional demo data/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Administration" })).toHaveAttribute(
      "href",
      "/admin/login",
    );
  });
});
