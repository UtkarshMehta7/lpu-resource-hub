import { useMemo, useState } from "react";

import type { CollaborationNetwork } from "./api";

const WIDTH = 720;
const HEIGHT = 420;
const RADIUS = 168;

const KIND_COLOUR: Record<string, string> = {
  co_authorship: "#1a5b65",
  project: "#8a6d1f",
  collaboration: "#6b4a8a",
};

/**
 * A dependency-free graph.
 *
 * People sit on a circle ordered by how connected they are, so the busiest
 * collaborators end up adjacent and their edges stay short. It's deliberately
 * not a force simulation: this is a readable picture of a department-sized
 * network, not a physics demo, and it renders identically every time.
 */
export function NetworkGraph({ graph }: { graph: CollaborationNetwork }) {
  const [focus, setFocus] = useState<string | null>(null);

  const positions = useMemo(() => {
    const connected = graph.nodes.filter((node) => node.connected);
    const ordered = [...connected].sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id));
    const map = new Map<string, { x: number; y: number }>();
    ordered.forEach((node, index) => {
      const angle = (index / Math.max(ordered.length, 1)) * Math.PI * 2 - Math.PI / 2;
      map.set(node.id, {
        x: WIDTH / 2 + RADIUS * Math.cos(angle),
        y: HEIGHT / 2 + RADIUS * Math.sin(angle),
      });
    });
    return map;
  }, [graph.nodes]);

  const visibleNodes = graph.nodes.filter((node) => positions.has(node.id));
  const isDimmed = (id: string) =>
    focus !== null &&
    focus !== id &&
    !graph.edges.some(
      (edge) =>
        (edge.source === focus && edge.target === id) ||
        (edge.target === focus && edge.source === id),
    );

  if (visibleNodes.length === 0) {
    return (
      <p className="rounded-card border border-line bg-surface px-4 py-8 text-center text-sm text-ink-muted">
        No connections yet. Co-authored publications, shared projects and accepted collaboration
        requests all draw a line here.
      </p>
    );
  }

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full rounded-card border border-line bg-surface"
        role="img"
        aria-label={`Collaboration network: ${visibleNodes.length} people, ${graph.edges.length} connections`}
      >
        {graph.edges.map((edge) => {
          const from = positions.get(edge.source);
          const to = positions.get(edge.target);
          if (!from || !to) return null;
          const dim = focus !== null && focus !== edge.source && focus !== edge.target;
          return (
            <line
              key={`${edge.source}-${edge.target}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={KIND_COLOUR[edge.kinds[0] ?? "project"] ?? "#8896a0"}
              strokeWidth={Math.min(1 + edge.weight, 4)}
              strokeOpacity={dim ? 0.12 : 0.5}
            />
          );
        })}
        {visibleNodes.map((node) => {
          const point = positions.get(node.id);
          if (!point) return null;
          const dim = isDimmed(node.id);
          return (
            <g
              key={node.id}
              opacity={dim ? 0.25 : 1}
              onMouseEnter={() => setFocus(node.id)}
              onMouseLeave={() => setFocus(null)}
              tabIndex={0}
              onFocus={() => setFocus(node.id)}
              onBlur={() => setFocus(null)}
            >
              <title>{`${node.full_name} · ${node.role.replace(/_/g, " ")} · ${node.degree} connection${node.degree === 1 ? "" : "s"}`}</title>
              <circle
                cx={point.x}
                cy={point.y}
                r={5 + Math.min(node.degree, 6)}
                fill={node.role === "student" ? "#8a6d1f" : "#1a5b65"}
              />
              <text
                x={point.x}
                y={point.y - 12 - Math.min(node.degree, 6)}
                textAnchor="middle"
                className="fill-ink text-[9px]"
              >
                {node.full_name}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-ink-muted">
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-brand-700" />
          Researcher
        </span>
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-[#8a6d1f]" />
          Student (opted in)
        </span>
        <span>Line colour shows how they are connected; thickness, how often.</span>
      </figcaption>
    </figure>
  );
}
