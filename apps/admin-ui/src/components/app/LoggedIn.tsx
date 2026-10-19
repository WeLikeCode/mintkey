/**
 * LoggedIn — AdminJS top-bar override that logs out through a CSRF-protected POST.
 *
 * AdminJS's default LoggedIn renders a "Log out" link that GETs paths.logoutPath,
 * which cannot carry the double-submit CSRF token. This override renders the
 * operator's email and a form posting to the logout route with a hidden `_csrf`
 * field. On submit the field takes the current `csrf_token` cookie value when it
 * is readable, so a page rendered before a later login still sends the token the
 * server compares.
 *
 * Registered in components/index.ts via componentLoader.override("LoggedIn", ...).
 */

import React from "react";

interface LoggedInSession {
  email?: string;
  csrfToken?: string;
}

interface LoggedInProps {
  session?: LoggedInSession;
  paths?: { logoutPath?: string };
}

function readCookie(header: string, name: string): string | undefined {
  for (const part of header.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() !== name) continue;
    const value = part.slice(separator + 1).trim();
    return value === "" ? undefined : value;
  }
  return undefined;
}

const LoggedIn: React.FC<LoggedInProps> = ({ session, paths }) => {
  const inputRef = React.useRef<HTMLInputElement>(null);

  const email = session?.email ?? "";
  const logoutPath = paths?.logoutPath ?? "/admin/logout";
  const initialToken = session?.csrfToken ?? "";

  const handleSubmit = (): void => {
    const currentToken = readCookie(document.cookie, "csrf_token");
    if (currentToken !== undefined && inputRef.current) {
      inputRef.current.value = currentToken;
    }
  };

  return (
    <span>
      <span>{email}</span>
      <form method="post" action={logoutPath} onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="hidden"
          name="_csrf"
          defaultValue={initialToken}
        />
        <button type="submit" data-testid="logout">
          Log out
        </button>
      </form>
    </span>
  );
};

export default LoggedIn;
