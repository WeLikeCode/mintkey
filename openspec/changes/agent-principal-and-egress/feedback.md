# Feedback — agent-principal-and-egress

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | addressed | behaviour |  | Refuse the IPv6 forms that carry an IPv4 address |
| FB-002 | addressed | behaviour |  | A malformed agent-supplied URL is refused, never an error |
| FB-003 | addressed | behaviour |  | The deny list matches names however they are written |
<!-- l4:feedback-index:end -->

---

## FB-001: Refuse the IPv6 forms that carry an IPv4 address

- **Status:** addressed
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T15:52:45Z

### Feedback
address_is_public relies on ip.is_global, which treats 64:ff9b::/96 as global (Python 3.13), while the proxy's guard refuses it; the two checks should refuse the same ranges.

### When / Then
- **When:** an agent-supplied base_url or openapi_url names a host that resolves to an address in 64:ff9b::/96 (NAT64), 2002::/16 (6to4) or 2001::/32 (Teredo)
- **Then:** the check refuses it with mintkey:target_not_allowed, on every supported Python version, so the create-time check refuses every range the proxy's connect-time guard refuses

### Outcome
<!-- written by the harness -->
Addressed in round 4 at 9040cfcf04: egress.py _IPV4_EMBEDDING_V6 and address_is_public refuse 64:ff9b::/96, 2002::/16, 2001::/32; test_C_0ed78ab3

---

## FB-002: A malformed agent-supplied URL is refused, never an error

- **Status:** addressed
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T15:52:46Z

### Feedback
Today a.example..com or a 64-character label raises UnicodeEncodeError from getaddrinfo (a 500), tabs and newlines are silently removed by urlsplit so the validated host differs from the stored URL, and 127.1 or 0x7f.1 reach the resolver.

### When / Then
- **When:** an agent-supplied URL's host has an empty label or a label longer than 63 characters, or the URL contains whitespace, a tab, a newline, any other control character, a percent sign or a backslash, or the host's last label is all decimal digits or 0x-hexadecimal
- **Then:** the check refuses it with mintkey:target_not_allowed and no unhandled exception reaches the caller

### Outcome
<!-- written by the harness -->
Addressed in round 4 at 9040cfcf04: egress.py _has_forbidden_character, _labels_are_valid, _NUMERIC_LAST_LABEL, and except (OSError, UnicodeError) around resolve_host

---

## FB-003: The deny list matches names however they are written

- **Status:** addressed
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T15:52:46Z

### Feedback
Only one trailing dot is removed from the host, entries are not normalised the same way, *.localhost is not in the built-in list, and an unusable entry silently protects nothing.

### When / Then
- **When:** the host or a MINTKEY_AGENT_EGRESS_DENY entry ends in one or more dots, or the host is localhost or under .localhost, or an entry can never match a name (`*`, `*.`, a leading dot, `*name` without a dot)
- **Then:** a host matches a deny entry exactly as the same name without its trailing dots, localhost and any name under .localhost are refused, and an entry that can never match is reported once in the log as ignored

### Outcome
<!-- written by the harness -->
Addressed in round 4 at 9040cfcf04: egress.py egress_deny_names rstrip('.') and _deny_entry_is_usable warning; host.endswith('.localhost') check in check_agent_target_url
