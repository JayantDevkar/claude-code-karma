<script lang="ts">
	import { Image } from 'lucide-svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import type { ImageAttachment } from '$lib/api-types';

	interface Props {
		attachments: ImageAttachment[];
		class?: string;
	}

	let { attachments, class: className = '' }: Props = $props();

	let modalOpen = $state(false);
	let selectedImage = $state<ImageAttachment | null>(null);

	function getExtension(mediaType: string): string {
		const parts = mediaType.split('/');
		const subtype = parts[1] || 'image';
		// Normalize common types
		if (subtype === 'jpeg') return 'JPG';
		return subtype.toUpperCase();
	}

	function openImage(attachment: ImageAttachment) {
		selectedImage = attachment;
		modalOpen = true;
	}

	function closeModal() {
		modalOpen = false;
		selectedImage = null;
	}
</script>

{#if attachments.length > 0}
	<div class="flex flex-wrap gap-2 mb-3 {className}">
		{#each attachments as attachment, i}
			<button
				type="button"
				onclick={() => openImage(attachment)}
				class="
					relative group rounded-lg
					border border-[var(--border)]
					overflow-hidden
					hover:border-[var(--accent)]
					transition-colors
					focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
				"
				title="Click to view full image"
				aria-label="View attached image {i + 1}"
			>
				<img
					src="data:{attachment.media_type};base64,{attachment.data}"
					class="w-20 h-20 object-cover"
					alt="Attached image {i + 1}"
				/>
				<!-- Type badge overlay -->
				<div class="absolute bottom-0 left-0 right-0 bg-black/50 px-1.5 py-0.5 flex items-center justify-between">
					<span class="text-[10px] font-medium text-white uppercase">
						{getExtension(attachment.media_type)}
					</span>
					<Image
						size={10}
						class="text-white/70 opacity-0 group-hover:opacity-100 transition-opacity"
					/>
				</div>
			</button>
		{/each}
	</div>

	<!-- Full-size image modal -->
	{#if selectedImage}
		{@const image = selectedImage}
		<Modal
			bind:open={modalOpen}
			onOpenChange={(open) => {
				if (!open) closeModal();
			}}
			title="Image Attachment"
			maxWidth="xl"
		>
			{#snippet children()}
				<div class="flex justify-center">
					<img
						src="data:{image.media_type};base64,{image.data}"
						class="max-h-[70vh] w-auto object-contain rounded-md"
						alt="Full size image attachment"
					/>
				</div>
				<div class="mt-3 pt-2 border-t border-[var(--border)]">
					<span class="text-xs text-[var(--text-muted)]">
						Type: {image.media_type}
					</span>
				</div>
			{/snippet}
		</Modal>
	{/if}
{/if}
