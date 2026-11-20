"""Repository Map + Architecture Map (New Plan §14.7 / §14.8).

**§14.8 Repository Map — the Aider methodology (MODE D/C).**
Aider-AI/aider was cloned + audited in ``vendor-staging/phase-14/``;
what NEXUS takes is the *method*, not a line of code:

1. Build a weighted graph over **files**: an edge A→B exists when
   file A references a symbol defined in file B (weight = number of
   references).
2. Run **PageRank** (damping 0.85 — Aider's choice, §127 of the
   Master Spec: «Files + Important symbols + Signatures +
   Relations»).
3. Personalize by file *interest* — Aider scales a file's rank by
   how much non-definition code it holds; NEXUS personalizes by its
   reference out-degree (the code that *does* something ranks
   higher than the code that only declares).
4. Render the map under a **token budget** — the ranked files, each
   with its key symbols and signatures, so the agent gets the
   architecture in a few hundred tokens instead of 400k lines.

    لا نرسل 400k سطر إلى النموذج — نرسل الخريطة.

**§14.7 Architecture Map** — the component view: files grouped by
their top-level directory, each component with file/symbol counts
and the aggregated dependency edges between components — the layers
the operator reads before the first edit.

خريطة المستودع بالترتيب (PageRank على مرجعيات الملفات) وخريطة
البنية بالمكوّنات — منهجية Aider بلا سطر واحد من كودها.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    CHARS_PER_TOKEN,
    PAGERANK_DAMPING,
    PAGERANK_ITERATIONS,
    PAGERANK_TOLERANCE,
    DependencyEdge,
    LayerEntry,
    MapEntry,
    Symbol,
)
from .store import SQLiteCodeIntelStore

#: Symbols rendered per map file (Aider keeps maps dense).
MAX_SYMBOLS_PER_FILE_IN_MAP = 8

#: Interest floor (a file with zero references still appears, tiny).
_MIN_INTEREST = 1e-9


@dataclass(slots=True)
class RepoMapResult:
    """The §14.8 render — entries + the honest token accounting."""

    entries: list[MapEntry]
    files_ranked: int
    files_rendered: int
    tokens_used: int
    token_budget: int

    def render(self) -> str:
        """The plain-text map (Aider's repomap format in spirit)."""
        blocks: list[str] = []
        for entry in self.entries:
            block = f"{entry.file}:"
            for line in entry.lines:
                block += f"\n  {line}"
            blocks.append(block)
        return "\n\n".join(blocks)

    def to_dict(self) -> dict[str, object]:
        return {
            "files_ranked": self.files_ranked,
            "files_rendered": self.files_rendered,
            "tokens_used": self.tokens_used,
            "token_budget": self.token_budget,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def pagerank(
    graph: dict[str, dict[str, float]],
    personalization: dict[str, float] | None = None,
    damping: float = PAGERANK_DAMPING,
    iterations: int = PAGERANK_ITERATIONS,
    tolerance: float = PAGERANK_TOLERANCE,
) -> dict[str, float]:
    """Weighted PageRank (Aider's §127 ranking core, NEXUS-native).

    ``graph`` — ``{node: {neighbor: weight}}`` (out-edges).
    ``personalization`` — per-node starting interest (sum-free; the
    vector is normalized here). Deterministic: plain dicts, sorted
    iteration order, zero randomness.
    """
    nodes = set(graph)
    for targets in graph.values():
        nodes.update(targets)
    if not nodes:
        return {}
    ordered = sorted(nodes)
    if personalization:
        total = sum(max(0.0, personalization.get(node, 0.0)) for node in ordered)
        if total > 0.0:
            base = {
                node: max(0.0, personalization.get(node, 0.0)) / total
                for node in ordered
            }
        else:
            base = {node: 1.0 / len(ordered) for node in ordered}
    else:
        base = {node: 1.0 / len(ordered) for node in ordered}
    out_weight = {
        node: sum(max(0.0, weight) for weight in graph.get(node, {}).values())
        for node in ordered
    }
    rank = dict(base)
    for _ in range(iterations):
        dangling = sum(rank[node] for node in ordered if out_weight[node] <= 0.0)
        inbound: dict[str, float] = {node: 0.0 for node in ordered}
        for node in ordered:
            if out_weight[node] <= 0.0:
                continue
            share = rank[node] / out_weight[node]
            for neighbor, weight in graph.get(node, {}).items():
                inbound[neighbor] += share * weight
        next_rank = {
            node: (1.0 - damping) * base[node]
            + damping * (inbound[node] + dangling * base[node])
            for node in ordered
        }
        delta = sum(abs(next_rank[node] - rank[node]) for node in ordered)
        rank = next_rank
        if delta < tolerance:
            break
    return rank


class RepositoryMap:
    """§14.8 — the ranked, budgeted, rendered repository map."""

    def __init__(self, store: SQLiteCodeIntelStore) -> None:
        self._store = store

    def file_scores(self) -> dict[str, float]:
        """PageRank over the reference graph (§127 methodology)."""
        edges = self._store.reference_edges()
        graph: dict[str, dict[str, float]] = {}
        for source, target, weight in edges:
            graph.setdefault(source, {})[target] = float(weight)
        # interest: reference out-degree (the personalization vector)
        out_degree: dict[str, float] = {}
        for source, targets in graph.items():
            out_degree[source] = float(sum(targets.values()))
        personalization = out_degree if out_degree else None
        return pagerank(graph, personalization)

    def build(
        self,
        token_budget: int = 1024,
        focus: list[str] | None = None,
    ) -> RepoMapResult:
        """Render the map under the token budget.

        ``focus`` — files to force into the head of the map (the
        Aider chat-file behavior: the files you are editing rank
        first, deterministically).
        """
        scores = self.file_scores()
        char_budget = max(1, token_budget) * CHARS_PER_TOKEN
        ranked_files = sorted(scores, key=lambda p: (-scores.get(p, 0.0), p))
        if focus:
            # Aider's chat-file behavior: the edited file leads the map
            # even when nothing references it — as long as it is indexed.
            # (A tree-sitter-less runtime extracts no JS references, so
            # "in scores" alone would drop the pin — the CI's catch.)
            wanted = [
                p
                for p in focus
                if p in scores or self._store.get_file(p) is not None
            ]
            ranked_files = wanted + [
                p for p in ranked_files if p not in wanted
            ]
        entries: list[MapEntry] = []
        used = 0
        for path in ranked_files:
            symbols = self._store.file_symbols(path)
            chosen = self._choose_symbols(symbols)
            lines = [
                f"{path}:",
                *(f"  {sym.signature or sym.kind + ' ' + sym.name}" for sym in chosen),
            ]
            block = "\n".join(lines)
            if used + len(block) + 2 > char_budget and entries:
                break
            entries.append(
                MapEntry(file=path, score=scores.get(path, 0.0), lines=lines[1:])
            )
            used += len(block) + 2
        return RepoMapResult(
            entries=entries,
            files_ranked=len(ranked_files),
            files_rendered=len(entries),
            tokens_used=(used + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN,
            token_budget=token_budget,
        )

    @staticmethod
    def _choose_symbols(symbols: list[Symbol]) -> list[Symbol]:
        """The map's per-file selection: rank weight, then line order."""
        ordered = sorted(symbols, key=lambda s: (-s.rank_weight, s.line, s.name))
        seen_kinds: dict[str, int] = {}
        chosen: list[Symbol] = []
        for sym in ordered:
            if len(chosen) >= MAX_SYMBOLS_PER_FILE_IN_MAP:
                break
            seen_kinds[sym.kind] = seen_kinds.get(sym.kind, 0) + 1
            chosen.append(sym)
        return sorted(chosen, key=lambda s: (s.line, s.name))


class ArchitectureMap:
    """§14.7 — the component/layer view of the whole project."""

    def __init__(self, store: SQLiteCodeIntelStore) -> None:
        self._store = store

    def build(self) -> list[LayerEntry]:
        """Files grouped by top-level directory → components.

        Root-level files land in the ``"."`` layer (entry scripts).
        Dependency edges aggregate between components.
        """
        layer_files: dict[str, int] = {}
        layer_symbols: dict[str, int] = {}
        for entry in self._store.all_files():
            path = entry.path
            layer = path.rsplit("/", 1)[0] if "/" in path else "."
            layer_files[layer] = layer_files.get(layer, 0) + 1
            layer_symbols[layer] = layer_symbols.get(layer, 0) + len(
                self._store.file_symbols(path)
            )
        edges: list[DependencyEdge] = self._store.all_edges()
        layer_deps: dict[str, dict[str, int]] = {layer: {} for layer in layer_files}
        for edge in edges:
            source_layer = edge.source.rsplit("/", 1)[0] if "/" in edge.source else "."
            target_layer = edge.target.rsplit("/", 1)[0] if "/" in edge.target else "."
            if source_layer == target_layer:
                continue
            layer_deps.setdefault(source_layer, {})
            layer_deps[source_layer][target_layer] = (
                layer_deps[source_layer].get(target_layer, 0) + 1
            )
        return [
            LayerEntry(
                layer=layer,
                files=layer_files[layer],
                symbols=layer_symbols[layer],
                depends_on=dict(
                    sorted(
                        layer_deps.get(layer, {}).items(),
                        key=lambda kv: (-kv[1], kv[0]),
                    )
                ),
            )
            for layer in sorted(layer_files)
        ]

    def render(self) -> str:
        """The plain-text architecture map."""
        lines: list[str] = []
        for layer in self.build():
            lines.append(f"[{layer.layer}] {layer.files} files, {layer.symbols} symbols")
            if layer.depends_on:
                deps = ", ".join(
                    f"{target}({count})"
                    for target, count in list(layer.depends_on.items())[:6]
                )
                lines.append(f"  depends on: {deps}")
        return "\n".join(lines)
