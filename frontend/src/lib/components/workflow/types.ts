/**
 * Shapes for the project decision workflow (GET /projects/{encoded}/workflow).
 *
 * A workflow is a set of threads. Each thread is one topic: a tier-1 `root`
 * (feature / milestone / scope / design) plus `nodes` — tier-2 events
 * (process / reversal / review) and tier-3 sub-nodes (waiver / correction).
 * `tier`, `label` and the `supersedes_*` fields are derived by the API.
 */

export interface WorkflowEvidence {
	type: 'commit' | 'pr' | 'session' | 'code' | 'memory' | 'link';
	label: string;
	url?: string;
	session_id?: string;
}

export interface WorkflowNode {
	id: string;
	kind: string;
	tier: 1 | 2 | 3;
	label: string;
	date: string;
	parent: string | null;
	session_id: string | null;
	session_title: string;
	decided_by: 'human' | 'ai' | 'both';
	status: 'active' | 'superseded';
	title: string;
	intent: string;
	options?: string[];
	chosen: string;
	why_quoted?: string;
	why_inferred?: string;
	supersedes?: string;
	supersedes_title?: string;
	supersedes_label?: string;
	evidence: WorkflowEvidence[];
}

export interface WorkflowThread {
	id: string;
	title: string;
	ordinal: number;
	root: WorkflowNode;
	nodes: WorkflowNode[];
}

export interface WorkflowData {
	project: string;
	period: string;
	curated_by?: string;
	threads: WorkflowThread[];
}
