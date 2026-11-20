# vendor-staging — external repository intake (Plan §0.2)

Everything cloned here went through (or is going through) the §0.2
intake cycle documented in **docs/REPOSITORY-INTEGRATION.md** — the
permanent record of licenses, security/architecture/compatibility
reviews, integration modes and version pins.

This directory is **gitignored by design**: clones are large and
re-fetchable from their pinned tags/commits; the *audit trail* is what
NEXUS keeps (in docs/, not in the working tree).

Current clones (all pins re-fetchable):

| Repo | Pin | Mode |
|---|---|---|
| `llama.cpp/` | tag b10829 · commit 5fdfa628 | B (ADAPT via llama-server) |
| `psutil/` | tag release-7.2.2 · commit 9eea97d | A (pip `[hardware]`) |
| `langgraph/` | tag 1.2.11 · commit 644815f | D (Phase-5 loop-shape reference) |
| `autogen/` | tag v0.4.4 · commit bd5a24b | D (Phase-5 registry/messaging reference) |
| `deepagents/` | tag deepagents==0.7.13 · commit 1aae374 | D (Phase-5 delegation reference) |
| `ecc/` | commit e04ea0b | B (Phase-6 skills/rules/hooks patterns) |
| `cline/` | commit c21b172 | B (Phase-6 session lifecycle patterns) |
| `langgraph/` (Round 3) | commit 81bf17b | B (Phase-6 checkpoint/durability patterns) |
| `prime-agent/` | commit 2ce4431 | D+B (Phase-6 goals/heartbeat patterns) |
| `deepagents/` (Round 3) | commit 07d2952 | D+B (Phase-6 skill-file contract) |
| `mcp-python-sdk/` | clone 08a3bc8 · **PyPI dist mcp 2.1.1 (v2 line)** | A (Phase-7 `[mcp]` extra behind the router) |
| `mcp-servers/` | commit d73f99e | B (Phase-7 §8.5 server launches: filesystem/git/fetch/memory) |
| `mcp-servers-archived/` | commit 9be4674 | B (Phase-7 §8.5 database = sqlite) |
| `windows-harness/` | commit 46a37cf | ADAPT (Phase-8 §9.2 transport contract, zero imports) |
| `pywinauto/` | commit 18d2a95 | A (Phase-8 §9.3 `[computer]` extra, lazy MODE A) |

Re-clone commands (exact pins):

```bash
git clone --depth 1 --branch b10829 --single-branch \
    https://github.com/ggml-org/llama.cpp.git llama.cpp
git clone --depth 1 --branch release-7.2.2 --single-branch \
    https://github.com/giampaolo/psutil.git psutil
git clone --depth 1 --branch 1.2.11 --single-branch \
    https://github.com/langchain-ai/langgraph.git langgraph
git clone --depth 1 --branch v0.4.4 --single-branch \
    https://github.com/microsoft/autogen.git autogen
git clone --depth 1 --branch "deepagents==0.7.13" --single-branch \
    https://github.com/langchain-ai/deepagents.git deepagents
# Round 3 (Phase 6 — fresh pins on main)
git clone --depth 1 --single-branch https://github.com/affaan-m/ecc.git ecc
git clone --depth 1 --single-branch https://github.com/cline/cline.git cline
git clone --depth 1 --single-branch https://github.com/langchain-ai/langgraph.git langgraph
git clone --depth 1 --single-branch https://github.com/PrimeIntellect-ai/prime-agent.git prime-agent
git clone --depth 1 --single-branch https://github.com/langchain-ai/deepagents.git deepagents
# Round 4 (Phase 7 — Tool System)
git clone --depth 1 --single-branch https://github.com/modelcontextprotocol/python-sdk.git mcp-python-sdk
git clone --depth 1 --single-branch https://github.com/modelcontextprotocol/servers.git mcp-servers
git clone --depth 1 --single-branch https://github.com/modelcontextprotocol/servers-archived.git mcp-servers-archived
# The SDK itself installs from PyPI (MODE A): pip install "nexus-core[mcp]" (mcp>=2.0,<3)
```

المستودعات الخارجية تدخل من هنا فقط — بدورة §0.2 الكاملة،
وبتثبيت الإصدار، وبسجل دائم في docs/REPOSITORY-INTEGRATION.md.

# Round 5 (Phase 8, Plan §9)
git clone --depth 1 https://github.com/browser-use/windows-harness
git clone --depth 1 https://github.com/pywinauto/pywinauto
