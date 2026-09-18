<script lang="ts">
	import Switch from '$lib/components/ui/Switch.svelte';
	import SelectDropdown from '$lib/components/ui/SelectDropdown.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SettingItem from '$lib/components/settings/SettingItem.svelte';
	import type { SettingManifestEntry } from '$lib/settings-manifest';

	interface Props {
		entry: SettingManifestEntry;
		value: unknown;
		saving: boolean;
		success: boolean;
		/** True when a prerequisite (e.g. a spell checker binary) is missing and the control should be disabled. */
		blocked?: boolean;
		blockedHint?: string;
		onchange: (value: string | boolean) => void;
		onreset: () => void;
	}

	let { entry, value, saving, success, blocked = false, blockedHint, onchange, onreset }: Props = $props();

	let isDefault = $derived(value === undefined || value === entry.default);

	function formatDefault(v: string | boolean | null): string {
		if (v === null) return 'unset';
		if (typeof v === 'boolean') return v ? 'On' : 'Off';
		return entry.options?.find((o) => o.value === v)?.label ?? v;
	}
</script>

<SettingItem
	title={entry.title}
	description={entry.description}
	hint={entry.hint}
	{saving}
	success={success ? 'Saved' : null}
	restartRequired={entry.restartRequired}
	defaultLabel={`Default: ${formatDefault(entry.default)}`}
	showReset={!isDefault}
	onReset={onreset}
	docsUrl={entry.docsUrl}
>
	{#snippet control()}
		<div class="flex flex-col items-end gap-1.5">
			{#if entry.type === 'boolean'}
				<Switch
					checked={Boolean(value ?? entry.default)}
					onCheckedChange={(checked) => onchange(checked)}
					disabled={saving || blocked}
				/>
			{:else if entry.type === 'enum'}
				<SelectDropdown
					options={entry.options ?? []}
					value={(value as string | undefined) ?? (entry.default as string)}
					onchange={(v) => onchange(String(v))}
					disabled={saving || blocked}
				/>
			{:else if entry.type === 'string'}
				<div>
					<TextInput
						value={(value as string | undefined) ?? ''}
						placeholder={entry.placeholder}
						list={entry.datalist ? `${entry.key}-suggestions` : undefined}
						oninput={(e) => {
							const next = (e.target as HTMLInputElement).value;
							// Clearing the field to empty should behave like Reset
							// (delete the key) rather than write a literal "" --
							// otherwise it silently diverges from what Reset does
							// even though both read as "unsetting" to the user.
							if (next === '') {
								onreset();
							} else {
								onchange(next);
							}
						}}
						disabled={saving}
						class="w-56 font-mono text-xs"
					/>
					{#if entry.datalist}
						<datalist id={`${entry.key}-suggestions`}>
							{#each entry.datalist as suggestion (suggestion)}
								<option value={suggestion}></option>
							{/each}
						</datalist>
					{/if}
				</div>
			{/if}
			{#if blocked && blockedHint}
				<p class="text-xs text-[var(--error)] max-w-[220px] text-right leading-relaxed">
					{blockedHint}
				</p>
			{/if}
		</div>
	{/snippet}
</SettingItem>
