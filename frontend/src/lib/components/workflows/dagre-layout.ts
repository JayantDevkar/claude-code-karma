import dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/svelte';

export function getLayoutedElements(
	nodes: Node[],
	edges: Edge[],
	direction: 'TB' | 'LR' = 'TB'
): { nodes: Node[]; edges: Edge[] } {
	const g = new dagre.graphlib.Graph();
	g.setDefaultEdgeLabel(() => ({}));
	g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 80 });

	nodes.forEach((node) => {
		g.setNode(node.id, { width: 200, height: 60 });
	});

	edges.forEach((edge) => {
		g.setEdge(edge.source, edge.target);
	});

	dagre.layout(g);

	return {
		nodes: nodes.map((node) => {
			const pos = g.node(node.id);
			return {
				...node,
				position: { x: pos.x - 100, y: pos.y - 30 }
			};
		}),
		edges
	};
}
