# Proposal: fix 2 for agent-principal-and-egress

## Why
Requested by CiprianSpot, 2026-11-27T15:52:45Z in FB-001 (behaviour): address_is_public relies on ip.is_global, which treats 64:ff9b::/96 as global (Python 3.13), while the proxy's guard refuses it; the two checks should refuse the same ranges.

Requested by CiprianSpot, 2026-11-27T15:52:46Z in FB-002 (behaviour): Today a.example..com or a 64-character label raises UnicodeEncodeError from getaddrinfo (a 500), tabs and newlines are silently removed by urlsplit so the validated host differs from the stored URL, and 127.1 or 0x7f.1 reach the resolver.

Requested by CiprianSpot, 2026-11-27T15:52:46Z in FB-003 (behaviour): Only one trailing dot is removed from the host, entries are not normalised the same way, *.localhost is not in the built-in list, and an unusable entry silently protects nothing.

The verifier found problems in `agent-principal-and-egress` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-479e3869 (major): Feedback FB-001 (behaviour): Refuse the IPv6 forms that carry an IPv4 address
- F-a34b91c1 (major): Feedback FB-002 (behaviour): A malformed agent-supplied URL is refused, never an error
- F-93283de1 (major): Feedback FB-003 (behaviour): The deny list matches names however they are written

## Impact
The code and the tests of `agent-principal-and-egress`.
