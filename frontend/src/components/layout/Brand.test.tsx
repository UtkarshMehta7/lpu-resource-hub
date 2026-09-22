import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Brand, PRODUCT_NAME, PRODUCT_SHORT, UNIVERSITY_NAME } from "./Brand";

describe("Brand", () => {
  it("shows the university name, the product name and the LPU shortform", () => {
    render(
      <MemoryRouter>
        <Brand />
      </MemoryRouter>,
    );

    expect(screen.getByText(UNIVERSITY_NAME)).toBeInTheDocument();
    expect(screen.getByText(PRODUCT_NAME)).toBeInTheDocument();
    // The short label is there for narrow screens.
    expect(screen.getByText(PRODUCT_SHORT)).toBeInTheDocument();
    // The prototype label travels with the mark.
    expect(screen.getByText(/prototype/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /research hub home/i })).toBeInTheDocument();
  });
});
