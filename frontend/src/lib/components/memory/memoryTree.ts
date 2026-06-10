/**
 * Build a folder tree from the flat /memory project list. Encoded project
 * names decode to filesystem paths, so projects naturally nest by their
 * shared path prefixes. Linear chains are compressed (a/b/c shown as one
 * node) so the tree stays shallow. Part of the ADDITIVE memory explorer.
 */

export interface MemoryProjectRow {
	encoded: string;
	label: string;
	path: string;
	note_count: number;
	has_index: boolean;
}

export interface MemoryTreeNode {
	name: string;
	children: MemoryTreeNode[];
	project: MemoryProjectRow | null;
	noteTotal: number;
}

function insert(root: MemoryTreeNode, row: MemoryProjectRow): void {
	const parts = row.path.split('/').filter(Boolean);
	let node = root;
	for (const part of parts) {
		let child = node.children.find((c) => c.name === part && !c.project);
		if (!child) {
			child = { name: part, children: [], project: null, noteTotal: 0 };
			node.children.push(child);
		}
		node = child;
	}
	node.project = row;
}

/** Collapse single-child, project-less chains: media → mktotoy → Shared → one node. */
function compress(node: MemoryTreeNode): MemoryTreeNode {
	node.children = node.children.map(compress);
	while (node.children.length === 1 && !node.project) {
		const only = node.children[0];
		node = {
			name: node.name ? `${node.name}/${only.name}` : only.name,
			children: only.children,
			project: only.project,
			noteTotal: 0
		};
	}
	return node;
}

function tallyNotes(node: MemoryTreeNode): number {
	const own = node.project?.note_count ?? 0;
	const sub = node.children.reduce((s, c) => s + tallyNotes(c), 0);
	node.noteTotal = own + sub;
	return node.noteTotal;
}

function sortTree(node: MemoryTreeNode): void {
	// folders first, then by note total desc, then name
	node.children.sort((a, b) => {
		const af = a.project && a.children.length === 0 ? 1 : 0;
		const bf = b.project && b.children.length === 0 ? 1 : 0;
		if (af !== bf) return af - bf;
		if (b.noteTotal !== a.noteTotal) return b.noteTotal - a.noteTotal;
		return a.name.localeCompare(b.name);
	});
	node.children.forEach(sortTree);
}

/** Build the compressed, sorted top-level nodes from the flat project list. */
export function buildMemoryTree(rows: MemoryProjectRow[]): MemoryTreeNode[] {
	const root: MemoryTreeNode = { name: '', children: [], project: null, noteTotal: 0 };
	for (const r of rows) insert(root, r);
	const compressed = root.children.map(compress);
	const top: MemoryTreeNode = { name: '', children: compressed, project: null, noteTotal: 0 };
	tallyNotes(top);
	sortTree(top);
	return top.children;
}
