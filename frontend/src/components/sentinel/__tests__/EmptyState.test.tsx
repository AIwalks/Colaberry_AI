import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState, LoadingState, ErrorState } from "../EmptyState";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="No reviews found" />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("No reviews found")).toBeInTheDocument();
  });

  it("renders optional body", () => {
    render(<EmptyState title="Empty" body="Nothing here yet" />);
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("renders default icon when not provided", () => {
    const { container } = render(<EmptyState title="Empty" />);
    expect(container).toHaveTextContent("○");
  });

  it("renders custom icon", () => {
    const { container } = render(<EmptyState title="Empty" icon="✓" />);
    expect(container).toHaveTextContent("✓");
  });

  it("omits body when not provided", () => {
    render(<EmptyState title="Just a title" />);
    expect(screen.queryByText(/body/i)).toBeNull();
  });
});

describe("LoadingState", () => {
  it("renders with default label", () => {
    render(<LoadingState />);
    expect(screen.getByTestId("loading-state")).toBeInTheDocument();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders with custom label", () => {
    render(<LoadingState label="Fetching reviews..." />);
    expect(screen.getByText("Fetching reviews...")).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("renders error message", () => {
    render(<ErrorState message="HTTP 500 Internal Server Error" />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500 Internal Server Error")).toBeInTheDocument();
  });

  it("renders heading text", () => {
    render(<ErrorState message="any error" />);
    expect(screen.getByText("Could not load data")).toBeInTheDocument();
  });
});
