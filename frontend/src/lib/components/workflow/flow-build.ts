/**
 * Turn the curated thread model into Svelte Flow `nodes` + `edges`.
 *
 * The initial layout is a swimlane per thread (root on the left, events along a
 * row, sub-events dropped below their parent) — a sensible starting arrangement
 * the user is then free to drag around the board.
 */

import { MarkerType, type Edge, type Node } from '@xyflow/svelte';
import type { WorkflowThread } from './types';

const LANE_H = 210; // vertical gap between threads
const LANE_Y0 = 24;
const ROOT_X = 0;
const COL_X0 = 300; // x of the first event in a lane
const COL_W = 190; // x-step between events
const SUB_DX = 30; // sub-node offset right of its parent
const SUB_DY = 128; // sub-node offset below its parent
const SUB_W = 150; // x-step between sibling sub-nodes

export interface WfNodeData {
	node: WorkflowThread['root'];
	threadTitle?: string;
	open: (id: string) => void;
	[key: string]: unknown;
}

export function buildGraph(
	threads: WorkflowThread[],
	open: (id: string) => void
): { nodes: Node[]; edges: Edge[] } {
	const nodes: Node[] = [];
	const edges: Edge[] = [];

	threads.forEach((thread, ti) => {
		const laneY = LANE_Y0 + ti * LANE_H;
		const events = thread.nodes.filter((n) => n.tier === 2);
		const subs = thread.nodes.filter((n) => n.tier === 3);

		nodes.push({
			id: thread.root.id,
			type: 'wf',
			position: { x: ROOT_X, y: laneY },
			data: { node: thread.root, threadTitle: thread.title, open }
		});

		const eventX = new Map<string, number>();
		events.forEach((n, k) => {
			const x = COL_X0 + k * COL_W;
			eventX.set(n.id, x);
			nodes.push({
				id: n.id,
				type: 'wf',
				position: { x, y: laneY },
				data: { node: n, open }
			});
			edges.push({
				id: `e-${n.id}`,
				source: n.parent ?? thread.root.id,
				target: n.id,
				sourceHandle: 'r-s',
				targetHandle: 'l-t',
				type: 'smoothstep'
			});
		});

		const seenPerParent = new Map<string, number>();
		subs.forEach((n) => {
			const pid = n.parent ?? thread.root.id;
			const idx = seenPerParent.get(pid) ?? 0;
			seenPerParent.set(pid, idx + 1);
			const px = eventX.get(pid) ?? ROOT_X;
			nodes.push({
				id: n.id,
				type: 'wf',
				position: { x: px + SUB_DX + idx * SUB_W, y: laneY + SUB_DY },
				data: { node: n, open }
			});
			edges.push({
				id: `e-${n.id}`,
				source: pid,
				target: n.id,
				sourceHandle: 'b-s',
				targetHandle: 't-t',
				type: 'smoothstep'
			});
		});

		for (const n of [thread.root, ...thread.nodes]) {
			if (!n.supersedes) continue;
			edges.push({
				id: `sup-${n.id}`,
				source: n.id,
				target: n.supersedes,
				sourceHandle: 't-s',
				targetHandle: 't-t',
				type: 'bezier',
				animated: true,
				label: 'supersedes',
				data: { supersedes: true },
				style: 'stroke: var(--warning, #f59e0b); stroke-width: 1.5; stroke-dasharray: 6 4;',
				markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--warning, #f59e0b)' }
			});
		}
	});

	return { nodes, edges };
}
