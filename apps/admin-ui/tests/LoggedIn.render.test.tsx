// @vitest-environment jsdom
/**
 * Red tests for the AdminJS LoggedIn top-bar override (task 5.1).
 *
 * `src/components/app/LoggedIn.tsx` and its registration in
 * `src/components/index.ts` are added in the green step. Until then the
 * component is absent; `import.meta.glob` yields no entry, so each render test
 * fails with a Vitest assertion instead of an unresolved-import error.
 */

import React from "react";
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";

const COMPONENT_MODULES = import.meta.glob("../src/components/app/LoggedIn.tsx");

const LOGOUT_PATH = "/admin/logout";

type LoggedInProps = {
  session: { email?: string; csrfToken?: string };
  paths: { logoutPath: string };
};

type LoggedInComponent = React.ComponentType<LoggedInProps>;

async function loadLoggedIn(): Promise<LoggedInComponent> {
  const keys = Object.keys(COMPONENT_MODULES);
  expect(
    keys,
    "src/components/app/LoggedIn.tsx must exist (task 5.1 green step)"
  ).toHaveLength(1);

  const loader = COMPONENT_MODULES[keys[0]] as () => Promise<{
    default?: LoggedInComponent;
  }>;
  const mod = await loader();

  expect(typeof mod.default).toBe("function");
  return mod.default as LoggedInComponent;
}

async function renderLoggedIn(session: LoggedInProps["session"]) {
  const LoggedIn = await loadLoggedIn();
  return render(
    React.createElement(LoggedIn, {
      session,
      paths: { logoutPath: LOGOUT_PATH },
    })
  );
}

function csrfInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[name="_csrf"]');
  expect(input, 'expected an input named "_csrf"').not.toBeNull();
  return input as HTMLInputElement;
}

function logoutForm(container: HTMLElement): HTMLFormElement {
  const form = container.querySelector("form");
  expect(form, "expected a logout form").not.toBeNull();
  return form as HTMLFormElement;
}

function clearCsrfCookie(): void {
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

afterEach(() => {
  cleanup();
  clearCsrfCookie();
});

describe("LoggedIn override — C-6d2b5e54 top bar form", () => {
  it("C-6d2b5e54: shows the email and a POST form with hidden _csrf and logout button, without a logout link", async () => {
    const { container } = await renderLoggedIn({
      email: "op@example.test",
      csrfToken: "tok",
    });

    expect(screen.getByText("op@example.test")).toBeInTheDocument();

    const form = logoutForm(container);
    expect(form.getAttribute("method")?.toLowerCase()).toBe("post");
    expect(form.getAttribute("action")).toBe(LOGOUT_PATH);

    const csrf = csrfInput(container);
    expect(csrf.getAttribute("type")).toBe("hidden");
    expect(csrf.value).toBe("tok");

    const button = screen.getByTestId("logout");
    expect(button.getAttribute("type")?.toLowerCase()).toBe("submit");

    expect(container.querySelector(`a[href="${LOGOUT_PATH}"]`)).toBeNull();
  });
});

describe("LoggedIn override — C-d34b4cb5 current CSRF cookie on submit", () => {
  it("C-d34b4cb5: submit replaces the rendered _csrf with the current csrf_token cookie", async () => {
    clearCsrfCookie();
    document.cookie = "csrf_token=fresh";

    const { container } = await renderLoggedIn({
      email: "op@example.test",
      csrfToken: "stale",
    });

    expect(csrfInput(container).value).toBe("stale");

    fireEvent.submit(logoutForm(container));

    expect(csrfInput(container).value).toBe("fresh");
  });
});

describe("LoggedIn override — C-5f6816da no CSRF token", () => {
  it("C-5f6816da: renders and submits an empty _csrf when session and cookie have no token", async () => {
    clearCsrfCookie();

    const { container } = await renderLoggedIn({ email: "op@example.test" });

    expect(screen.getByText("op@example.test")).toBeInTheDocument();
    const form = logoutForm(container);
    expect(form.getAttribute("action")).toBe(LOGOUT_PATH);
    expect(csrfInput(container).value).toBe("");

    fireEvent.submit(form);

    expect(csrfInput(container).value).toBe("");
  });
});
