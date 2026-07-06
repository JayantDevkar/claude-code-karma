<script lang="ts">
	interface Props {
		path: string;
		oldString: string;
		newString: string;
	}

	let { path, oldString, newString }: Props = $props();

	// Build a line-by-line unified diff
	interface DiffLine {
		type: 'context' | 'removed' | 'added';
		text: string;
		oldNum?: number;
		newNum?: number;
	}

	function computeDiff(oldText: string, newText: string): DiffLine[] {
		const oldLines = oldText.split('\n');
		const newLines = newText.split('\n');

		// Simple LCS-based diff
		const m = oldLines.length;
		const n = newLines.length;

		// DP table for LCS lengths
		const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
		for (let i = m - 1; i >= 0; i--) {
			for (let j = n - 1; j >= 0; j--) {
				if (oldLines[i] === newLines[j]) {
					dp[i][j] = dp[i + 1][j + 1] + 1;
				} else {
					dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
				}
			}
		}

		// Trace back to build diff
		const result: DiffLine[] = [];
		let i = 0, j = 0;
		let oldNum = 1, newNum = 1;

		while (i < m || j < n) {
			if (i < m && j < n && oldLines[i] === newLines[j]) {
				result.push({ type: 'context', text: oldLines[i], oldNum, newNum });
				i++; j++; oldNum++; newNum++;
			} else if (j < n && (i >= m || dp[i][j + 1] >= dp[i + 1][j])) {
				result.push({ type: 'added', text: newLines[j], newNum });
				j++; newNum++;
			} else {
				result.push({ type: 'removed', text: oldLines[i], oldNum });
				i++; oldNum++;
			}
		}
		return result;
	}

	const diffLines = $derived(computeDiff(oldString, newString));
	const fileName = $derived(path.split('/').at(-1) ?? path);

	// Stats
	const added = $derived(diffLines.filter((l) => l.type === 'added').length);
	const removed = $derived(diffLines.filter((l) => l.type === 'removed').length);
</script>

<div class="flex flex-col h-full font-mono text-xs">
	<!-- File header -->
	<div class="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)] bg-[var(--bg-subtle)]">
		<span class="text-[var(--text-primary)] font-semibold">{fileName}</span>
		<span class="text-[var(--text-faint)] text-[10px] truncate flex-1">{path}</span>
		<span class="text-[#4ade80] font-mono text-[11px]">+{added}</span>
		<span class="text-[#f87171] font-mono text-[11px]">−{removed}</span>
	</div>

	<!-- Diff lines -->
	<div class="flex-1 overflow-y-auto">
		{#if diffLines.length === 0}
			<div class="flex items-center justify-center h-32 text-[var(--text-faint)]">
				No changes
			</div>
		{:else}
			<table class="w-full border-collapse">
				<tbody>
					{#each diffLines as line}
						<tr class="
							{line.type === 'added' ? 'bg-[#16391f]' : ''}
							{line.type === 'removed' ? 'bg-[#3b1212]' : ''}
							{line.type === 'context' ? 'bg-[var(--bg-base)]' : ''}
							hover:brightness-110 transition-none
						">
							<!-- Old line number -->
							<td class="select-none text-right px-2 py-0.5 text-[10px] text-[var(--text-faint)] w-10 border-r border-[var(--border)]/30 tabular-nums">
								{line.oldNum ?? ''}
							</td>
							<!-- New line number -->
							<td class="select-none text-right px-2 py-0.5 text-[10px] text-[var(--text-faint)] w-10 border-r border-[var(--border)]/30 tabular-nums">
								{line.newNum ?? ''}
							</td>
							<!-- Gutter char -->
							<td class="select-none px-2 py-0.5 w-6 text-center
								{line.type === 'added' ? 'text-[#4ade80]' : ''}
								{line.type === 'removed' ? 'text-[#f87171]' : ''}
								{line.type === 'context' ? 'text-[var(--text-faint)]' : ''}
							">
								{line.type === 'added' ? '+' : line.type === 'removed' ? '−' : ' '}
							</td>
							<!-- Content -->
							<td class="px-3 py-0.5 whitespace-pre-wrap break-all
								{line.type === 'added' ? 'text-[#86efac]' : ''}
								{line.type === 'removed' ? 'text-[#fca5a5]' : ''}
								{line.type === 'context' ? 'text-[var(--text-secondary)]' : ''}
							">
								{line.text}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>
