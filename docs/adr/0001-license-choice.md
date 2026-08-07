# ADR 0001: License choice — AGPL-3.0

## Status

Accepted.

## Context

Reeler is positioned as an open-source alternative to commercial AI
short-video tools. A common failure mode for projects like this is a
well-funded fork running the code as a closed-source hosted service without
contributing improvements back.

## Decision

License the project under **AGPL-3.0-or-later**.

AGPL's network-use clause means anyone who modifies Reeler and runs it as a
network service (e.g. a competing SaaS) must also make their modified
source available to users of that service — unlike plain GPL, which only
triggers on distribution of the software itself, not on running it as a
service.

## Alternatives considered

- **Apache-2.0**: fully permissive, allows closed-source commercial forks
  with only attribution required. Maximizes adoption and contribution
  ease, but gives up any protection against exactly the failure mode
  described above.
- **MIT**: even more permissive/minimal than Apache-2.0, same trade-off.

## Consequences

- Contributors and downstream users must be comfortable with AGPL's terms,
  which are more restrictive than a permissive license — this may reduce
  adoption by companies wary of AGPL dependencies.
- If Reeler itself ever offers a hosted version, that version is bound by
  the same terms — consistent with the project's stated open-source-first
  goal.
- This decision is revisitable — if broader adoption ends up mattering more
  than fork protection, a future ADR can propose relicensing (which would
  require contributor agreement, since relicensing needs consent from
  everyone who holds copyright on existing contributions).
