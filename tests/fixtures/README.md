# Offline fixture provenance

Current fixtures are synthetic and constructed directly in the Python tests and
`rwf/pilot_synthetic.py`; there are no copied real API responses in this directory.
Schema tests build a minimal artificial GraphQL schema, introspect it in memory,
and check temporary queries. Transport tests inject responses; pilot tests use
invented character/actor/item examples and a virtual clock.

In-memory OAuth tests use exact dummy markers to exercise token exclusion from
archives. They are not provider credentials. Hygiene checks exempt specific dummy
strings in specific existing source/test files. Saved fixtures must contain no
authentication fields, even with dummy values.

Before adding a fixture file:

1. Prefer an invented minimal example representing the required behavior.
2. For a provider-derived example, document source URL/API operation, capture date,
   redistribution review, transformation steps, and behavior under test here.
3. Remove tokens, headers, cookies, client IDs/secrets, request identifiers, absolute
   paths, usernames, actual character/report identifiers, and unrelated metadata.
   Replace identities with stable invented values and preserve necessary shapes only.
4. Keep content small, deterministic UTF-8; preserve null/missing/empty distinctions
   when relevant. Do not copy full schemas or bulk archives just to satisfy tests.
5. Review staged bytes and run hygiene/offline tests. Ignoring a raw source file
   is not sanitization of a derived fixture.

Raw feasibility schemas/payloads are local compatibility evidence, not fixtures.
