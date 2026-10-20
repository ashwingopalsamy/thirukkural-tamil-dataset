# Security policy

## Reporting a vulnerability

Do not report vulnerabilities in public issues. Use a private [security advisory](https://github.com/ashwingopalsamy/thirukkural-tamil-dataset/security/advisories/new).

Include the affected commit or version, steps to reproduce, and the impact.

## Scope

- `tkcore/` and `scripts/`, including the MCP server (`python -m tkcore.mcp_server`) and the HTTP tool server (`python -m tkcore.agent_tools serve`)
- the integrity data of a release: `text_sha256`, `MANIFEST.json` and the Merkle proofs

## Integrity

Every kural has a `text_sha256`, every release file a sha256 in `MANIFEST.json`, and every kural a Merkle proof against the roots in the dataset card. A mismatch is a security report, not a bug report.

## Response

1. Acknowledge the report.
2. Confirm it and assess the impact.
3. Fix it and release.
4. Disclose it after the fix is released.
