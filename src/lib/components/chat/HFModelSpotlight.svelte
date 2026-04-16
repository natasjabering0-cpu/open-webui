<script lang="ts">
	import { getContext, tick } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import type { HFDeploymentBundle, HFModelItem, HFTemplateSpec } from '$lib/apis/hf-models';
	import {
		createHFDeploymentBundle,
		createHFTemplateSpec,
		getHFModels
	} from '$lib/apis/hf-models';

	const i18n = getContext('i18n');

	export let show = false;
	export let initialPanel: 'browse' | 'deploy' = 'browse';

	const STORAGE_KEY = 'master-hf-spotlight-models';

	let wasOpen = false;
	let searchInputElement: HTMLInputElement;
	let searchTimeout: ReturnType<typeof setTimeout> | null = null;

	let panel: 'browse' | 'deploy' = 'browse';
	let query = '';
	let sort: 'newest' | 'best-rated' = 'newest';
	let loading = false;
	let items: HFModelItem[] = [];
	let total = 0;

	let selectedModelIds: string[] = [];
	let activeModelId = '';

	let template: 'simple-agent' | 'RAG-agent' = 'RAG-agent';
	let memory = true;
	let tools = 'retrieval';

	let previewTitle = '';
	let previewBody = '';
	let bundlePreview: HFDeploymentBundle | null = null;

	const openSpotlight = async () => {
		panel = initialPanel;
		restoreSelections();
		await loadModels();
		await tick();
		searchInputElement?.focus();
	};

	const restoreSelections = () => {
		try {
			const restored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
			selectedModelIds = Array.isArray(restored) ? restored.filter((item) => typeof item === 'string') : [];
		} catch {
			selectedModelIds = [];
		}

		if (!selectedModelIds.includes(activeModelId)) {
			activeModelId = selectedModelIds[0] ?? '';
		}
	};

	const persistSelections = () => {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedModelIds));
	};

	const loadModels = async () => {
		loading = true;
		try {
			const response = await getHFModels({
				query,
				sort,
				compatibleOnly: true,
				limit: 40
			});
			items = response.items;
			total = response.total;

			if (!activeModelId && selectedModelIds.length > 0) {
				activeModelId = selectedModelIds[0];
			}
		} catch (error) {
			toast.error(`${error}`);
		} finally {
			loading = false;
		}
	};

	const getModel = (modelId: string) => items.find((item) => item.model_id === modelId);

	const queueLoad = () => {
		if (searchTimeout) {
			clearTimeout(searchTimeout);
		}

		searchTimeout = setTimeout(async () => {
			await loadModels();
		}, 150);
	};

	const toggleSelection = (modelId: string) => {
		if (selectedModelIds.includes(modelId)) {
			selectedModelIds = selectedModelIds.filter((id) => id !== modelId);
			if (activeModelId === modelId) {
				activeModelId = selectedModelIds[0] ?? '';
			}
		} else {
			selectedModelIds = [modelId, ...selectedModelIds.filter((id) => id !== modelId)];
			activeModelId = modelId;
		}

		persistSelections();
	};

	const createToolsPayload = () =>
		tools
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);

	const startRag = async () => {
		if (!activeModelId) {
			toast.error($i18n.t('Select a model first'));
			return;
		}

		panel = 'deploy';
		template = 'RAG-agent';
		memory = true;
		try {
			const spec: HFTemplateSpec = await createHFTemplateSpec({
				template: 'RAG-agent',
				model: activeModelId,
				memory: true,
				tools: createToolsPayload()
			});

			previewTitle = `${$i18n.t('RAG setup ready')}: ${spec.model}`;
			previewBody = JSON.stringify(spec, null, 2);
			bundlePreview = null;
			toast.success($i18n.t('RAG setup initialized'));
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	const deploySelected = async () => {
		if (!activeModelId) {
			toast.error($i18n.t('Select a model first'));
			return;
		}

		try {
			const bundle = await createHFDeploymentBundle({
				template,
				model: activeModelId,
				memory,
				tools: createToolsPayload()
			});

			bundlePreview = bundle;
			previewTitle = `${$i18n.t('Deploy bundle ready')}: ${bundle.spec.model}`;
			previewBody = bundle.config_json;
			panel = 'deploy';
			toast.success($i18n.t('Deploy bundle generated'));
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	const downloadConfig = () => {
		if (!bundlePreview) {
			return;
		}

		const blob = new Blob([bundlePreview.config_json], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = 'config.json';
		anchor.click();
		URL.revokeObjectURL(url);
	};

	$: if (show && !wasOpen) {
		wasOpen = true;
		void openSpotlight();
	}

	$: if (!show && wasOpen) {
		wasOpen = false;
	}
</script>

<Modal bind:show size="lg" className="bg-white dark:bg-gray-900 rounded-3xl" containerClassName="p-3 md:p-8">
	<div class="flex flex-col max-h-[85vh]">
		<div class="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
			<div>
				<h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
					HF Spotlight
				</h2>
				<p class="text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Find, sort, add/remove, start RAG, and deploy from the chat window')}
				</p>
			</div>

			<div class="flex items-center gap-2 rounded-2xl bg-gray-100 dark:bg-gray-850 p-1">
				<button
					class="px-3 py-1.5 rounded-xl text-sm {panel === 'browse'
						? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
						: 'text-gray-500 dark:text-gray-400'}"
					on:click={() => {
						panel = 'browse';
					}}
				>
					HF
				</button>
				<button
					class="px-3 py-1.5 rounded-xl text-sm {panel === 'deploy'
						? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
						: 'text-gray-500 dark:text-gray-400'}"
					on:click={() => {
						panel = 'deploy';
					}}
				>
					Deploy
				</button>
			</div>
		</div>

		<div class="px-5 pb-4">
			<div
				class="flex items-center gap-3 rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-4 py-3 shadow-xs"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.8"
					class="size-4 text-gray-500 dark:text-gray-400"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="m21 21-4.35-4.35" />
					<circle cx="11" cy="11" r="6" />
				</svg>

				<input
					bind:this={searchInputElement}
					bind:value={query}
					class="w-full bg-transparent text-base outline-hidden text-gray-900 dark:text-gray-100 placeholder:text-gray-400"
					placeholder={$i18n.t('Search Hugging Face model ids')}
					on:input={queueLoad}
					on:keydown={async (event) => {
						if (event.key === 'Enter' && items[0]) {
							toggleSelection(items[0].model_id);
						}
					}}
				/>

				<div class="flex items-center gap-2">
					<button
						class="px-3 py-1.5 rounded-xl text-sm {sort === 'newest'
							? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
							: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300'}"
						on:click={async () => {
							sort = 'newest';
							await loadModels();
						}}
					>
						Nyest
					</button>
					<button
						class="px-3 py-1.5 rounded-xl text-sm {sort === 'best-rated'
							? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
							: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300'}"
						on:click={async () => {
							sort = 'best-rated';
							await loadModels();
						}}
					>
						Bedst bedømte
					</button>
				</div>
			</div>
		</div>

		<div class="px-5 pb-3">
			<div class="flex flex-wrap items-center gap-2">
				<span class="text-xs font-medium uppercase tracking-wide text-gray-400">
					Valgte modeller
				</span>

				{#if selectedModelIds.length === 0}
					<span class="text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t('No models selected yet')}
					</span>
				{:else}
					{#each selectedModelIds as modelId}
						<button
							class="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm {activeModelId ===
							modelId
								? 'border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-500/10 dark:text-blue-300'
								: 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200'}"
							on:click={() => {
								activeModelId = modelId;
							}}
						>
							<span class="max-w-[18rem] truncate">{modelId}</span>
							<span
								class="text-gray-400 hover:text-red-500"
								on:click|stopPropagation={() => {
									toggleSelection(modelId);
								}}
							>
								×
							</span>
						</button>
					{/each}
				{/if}
			</div>
		</div>

		<div class="grid grid-cols-1 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] gap-0 border-t border-gray-100 dark:border-gray-850 min-h-0">
			<div class="min-h-0 border-b lg:border-b-0 lg:border-r border-gray-100 dark:border-gray-850">
				<div class="flex items-center justify-between px-5 py-3 text-sm text-gray-500 dark:text-gray-400">
					<span>{total} modeller</span>
					<span>{$i18n.t('Only llama.cpp-compatible models are shown')}</span>
				</div>

				<div class="max-h-[26rem] overflow-y-auto px-3 pb-3">
					{#if loading}
						<div class="px-3 py-6 text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('Loading models...')}
						</div>
					{:else if items.length === 0}
						<div class="px-3 py-6 text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('No matching deployable models found')}
						</div>
					{:else}
						{#each items as item}
							<div
								class="flex items-start justify-between gap-3 rounded-2xl px-3 py-3 hover:bg-gray-50 dark:hover:bg-gray-850/80 {activeModelId ===
								item.model_id
									? 'bg-gray-50 dark:bg-gray-850/80'
									: ''}"
							>
								<button
									class="flex-1 min-w-0 text-left"
									on:click={() => {
										activeModelId = item.model_id;
									}}
								>
									<div class="flex items-center gap-2">
										<span class="truncate font-medium text-gray-900 dark:text-gray-100">
											{item.model_id}
										</span>
										<span class="rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-[11px] text-gray-500 dark:text-gray-400">
											{item.format ?? 'GGUF'}
										</span>
										{#if item.quantization}
											<span class="rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-[11px] text-gray-500 dark:text-gray-400">
												{item.quantization}
											</span>
										{/if}
									</div>
									<div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
										<span>↑ {item.likes}</span>
										<span>↓ {item.downloads}</span>
										{#if item.upload_date}
											<span>{item.upload_date.slice(0, 10)}</span>
										{/if}
										{#each item.tags.slice(0, 3) as tag}
											<span class="rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5">{tag}</span>
										{/each}
									</div>
								</button>

								<button
									class="shrink-0 rounded-xl px-3 py-2 text-sm {selectedModelIds.includes(item.model_id)
										? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300'
										: 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'}"
									on:click={() => {
										toggleSelection(item.model_id);
									}}
								>
									{selectedModelIds.includes(item.model_id) ? 'Fjern' : 'Add'}
								</button>
							</div>
						{/each}
					{/if}
				</div>
			</div>

			<div class="min-h-0 flex flex-col">
				<div class="px-5 py-4 border-b border-gray-100 dark:border-gray-850">
					<div class="flex items-center justify-between gap-3">
						<div>
							<div class="text-xs font-medium uppercase tracking-wide text-gray-400">
								Aktiv model
							</div>
							<div class="mt-1 text-sm font-medium text-gray-900 dark:text-gray-100">
								{activeModelId || $i18n.t('Choose a model')}
							</div>
						</div>

						<div class="flex items-center gap-2 rounded-2xl bg-gray-100 dark:bg-gray-850 p-1">
							<button
								class="px-3 py-1.5 rounded-xl text-sm {template === 'simple-agent'
									? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
									: 'text-gray-500 dark:text-gray-400'}"
								on:click={() => {
									template = 'simple-agent';
								}}
							>
								Simple
							</button>
							<button
								class="px-3 py-1.5 rounded-xl text-sm {template === 'RAG-agent'
									? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
									: 'text-gray-500 dark:text-gray-400'}"
								on:click={() => {
									template = 'RAG-agent';
								}}
							>
								RAG
							</button>
						</div>
					</div>

					<div class="mt-4 space-y-3">
						<label class="flex items-center justify-between gap-3 rounded-2xl bg-gray-50 dark:bg-gray-850/80 px-3 py-2">
							<span class="text-sm text-gray-600 dark:text-gray-300">Memory</span>
							<input bind:checked={memory} type="checkbox" class="size-4" />
						</label>

						<input
							bind:value={tools}
							class="w-full rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
							placeholder="retrieval, calculator"
						/>
					</div>

					<div class="mt-4 grid grid-cols-2 gap-2">
						<button
							class="rounded-2xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
							disabled={!activeModelId}
							on:click={startRag}
						>
							Start RAG
						</button>
						<button
							class="rounded-2xl bg-gray-900 px-4 py-2.5 text-sm font-medium text-white dark:bg-gray-100 dark:text-gray-900 disabled:opacity-50"
							disabled={!activeModelId}
							on:click={deploySelected}
						>
							Deploy
						</button>
					</div>
				</div>

				<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
					<div class="flex items-center justify-between gap-3">
						<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
							{previewTitle || $i18n.t('Preview')}
						</div>
						{#if bundlePreview}
							<button
								class="rounded-xl border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300"
								on:click={downloadConfig}
							>
								Download config.json
							</button>
						{/if}
					</div>

					{#if bundlePreview}
						<div class="mt-3 rounded-2xl bg-gray-50 dark:bg-gray-950 border border-gray-100 dark:border-gray-850 p-3">
							<div class="text-xs uppercase tracking-wide text-gray-400">Runtime</div>
							<div class="mt-2 space-y-1 text-sm text-gray-600 dark:text-gray-300">
								{#each bundlePreview.runtime_notes as note}
									<div>{note}</div>
								{/each}
							</div>
						</div>
					{/if}

					<pre class="mt-3 overflow-x-auto rounded-2xl bg-gray-50 dark:bg-gray-950 border border-gray-100 dark:border-gray-850 p-4 text-xs text-gray-700 dark:text-gray-200">{previewBody || $i18n.t('Select a model and use Start RAG or Deploy')}</pre>
				</div>
			</div>
		</div>
	</div>
</Modal>
