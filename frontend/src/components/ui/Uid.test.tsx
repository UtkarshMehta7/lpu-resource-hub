import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Uid } from "./Uid";

describe("Uid", () => {
  it("shows the registration number beside the name", () => {
    render(
      <p>
        Demo Faculty 07 <Uid value="DEMOFACULTY07" />
      </p>,
    );

    expect(screen.getByText("DEMOFACULTY07")).toBeInTheDocument();
  });

  it("renders nothing rather than an empty badge when there is no number", () => {
    const { container } = render(<Uid value="" />);

    expect(container).toBeEmptyDOMElement();
  });
});
