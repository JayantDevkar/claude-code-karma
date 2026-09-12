/**
 * The decision-workflow taxonomy: three tiers, narrowing.
 *
 *   Tier 1 — Topics     feature · milestone · scope · design
 *   Tier 2 — Events      process · reversal · review
 *   Tier 3 — Sub-events  waiver · correction
 *
 * Each kind is drawn with its own shape + initial so the diagram reads without
 * relying on colour. Colours are a secondary channel and live here so a design
 * pass can retune them in one place.
 */

export type Tier = 1 | 2 | 3;

export type ShapeName =
	| 'roundedRect'
	| 'diamond'
	| 'trapezoid'
	| 'parallelogram'
	| 'circle'
	| 'hexagon'
	| 'square'
	| 'pill';

export interface KindMeta {
	kind: string;
	tier: Tier;
	word: string;
	initial: string;
	shape: ShapeName;
	color: string;
	gloss: string;
}

export const KIND_META: Record<string, KindMeta> = {
	feature: {
		kind: 'feature',
		tier: 1,
		word: 'Feature',
		initial: 'F',
		shape: 'roundedRect',
		color: '#8b5cf6',
		gloss: 'A capability the project decided to build'
	},
	milestone: {
		kind: 'milestone',
		tier: 1,
		word: 'Milestone',
		initial: 'M',
		shape: 'diamond',
		color: '#10b981',
		gloss: 'A shipping or achievement marker'
	},
	scope: {
		kind: 'scope',
		tier: 1,
		word: 'Scope',
		initial: 'S',
		shape: 'trapezoid',
		color: '#0ea5e9',
		gloss: 'What is in or out of bounds for a piece of work'
	},
	design: {
		kind: 'design',
		tier: 1,
		word: 'Design',
		initial: 'D',
		shape: 'parallelogram',
		color: '#ec4899',
		gloss: 'How something should look or behave'
	},
	process: {
		kind: 'process',
		tier: 2,
		word: 'Process',
		initial: 'P',
		shape: 'circle',
		color: '#64748b',
		gloss: 'A step taken while working the topic'
	},
	reversal: {
		kind: 'reversal',
		tier: 2,
		word: 'Reversal',
		initial: 'Rv',
		shape: 'hexagon',
		color: '#f97316',
		gloss: 'A decision that undoes or changes an earlier one'
	},
	review: {
		kind: 'review',
		tier: 2,
		word: 'Review',
		initial: 'R',
		shape: 'square',
		color: '#6366f1',
		gloss: 'A review pass over the work'
	},
	waiver: {
		kind: 'waiver',
		tier: 3,
		word: 'Waiver',
		initial: 'W',
		shape: 'pill',
		color: '#f59e0b',
		gloss: 'A review finding consciously dismissed, with reason'
	},
	correction: {
		kind: 'correction',
		tier: 3,
		word: 'Correction',
		initial: 'C',
		shape: 'pill',
		color: '#ef4444',
		gloss: 'A wrong assumption or real bug caught and fixed'
	}
};

/** Rows of the inverted-pyramid key, widest first. */
export const TIER_ROWS: string[][] = [
	['feature', 'milestone', 'scope', 'design'],
	['process', 'reversal', 'review'],
	['waiver', 'correction']
];

export const TIER_NAMES = ['Topic', 'Event', 'Sub-event'];

export function metaFor(kind: string): KindMeta {
	return KIND_META[kind] ?? KIND_META.process;
}

/** Fill for a node body — the kind colour dropped onto the page background. */
export function fillFor(kind: string): string {
	return `color-mix(in srgb, ${metaFor(kind).color} 15%, var(--bg-base))`;
}

export interface ShapeSpec {
	el: 'rect' | 'circle' | 'polygon';
	attrs: Record<string, string | number>;
}

/**
 * Geometry for one glyph centred at (cx, cy) fitting a `size`-wide box.
 * Shared by the key, the drawer header and the flowchart so every shape is
 * defined exactly once.
 */
export function shapeSpec(shape: ShapeName, cx: number, cy: number, size: number): ShapeSpec {
	const h = size / 2;
	switch (shape) {
		case 'circle':
			return { el: 'circle', attrs: { cx, cy, r: h } };
		case 'square':
			return {
				el: 'rect',
				attrs: { x: cx - h, y: cy - h, width: size, height: size, rx: 4 }
			};
		case 'roundedRect':
			return {
				el: 'rect',
				attrs: { x: cx - size * 0.64, y: cy - h, width: size * 1.28, height: size, rx: 10 }
			};
		case 'pill':
			return {
				el: 'rect',
				attrs: {
					x: cx - size * 0.74,
					y: cy - size * 0.32,
					width: size * 1.48,
					height: size * 0.64,
					rx: size * 0.32
				}
			};
		case 'diamond':
			return {
				el: 'polygon',
				attrs: { points: `${cx},${cy - h} ${cx + h},${cy} ${cx},${cy + h} ${cx - h},${cy}` }
			};
		case 'trapezoid':
			return {
				el: 'polygon',
				attrs: {
					points: `${cx - h * 0.58},${cy - h} ${cx + h * 0.58},${cy - h} ${cx + h},${cy + h} ${cx - h},${cy + h}`
				}
			};
		case 'parallelogram':
			return {
				el: 'polygon',
				attrs: {
					points: `${cx - h * 0.55},${cy - h} ${cx + h},${cy - h} ${cx + h * 0.55},${cy + h} ${cx - h},${cy + h}`
				}
			};
		case 'hexagon': {
			const q = h * 0.55;
			return {
				el: 'polygon',
				attrs: {
					points: `${cx - h},${cy} ${cx - q},${cy - h} ${cx + q},${cy - h} ${cx + h},${cy} ${cx + q},${cy + h} ${cx - q},${cy + h}`
				}
			};
		}
	}
}
