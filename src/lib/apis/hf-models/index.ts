import { WEBUI_API_BASE_URL } from '$lib/constants';

type HFSort = 'newest' | 'best-rated' | 'oldest';

type HFTemplate = 'simple-agent' | 'RAG-agent';

export type HFModelItem = {
	model_id: string;
	format?: string | null;
	quantization?: string | null;
	tags: string[];
	size?: string | null;
	upload_date?: string | null;
	likes: number;
	downloads: number;
	huggingface_url: string;
	llama_cpp_compatible: boolean;
	is_favorite: boolean;
};

export type HFModelsResponse = {
	items: HFModelItem[];
	total: number;
	sort: HFSort;
	available_filters: {
		tags: string[];
		formats: string[];
		quantizations: string[];
	};
	available_sorts: HFSort[];
	last_synced_at?: string | null;
};

export type HFTemplateSpec = {
	template: HFTemplate;
	model: string;
	runtime: 'llama.cpp';
	memory: boolean;
	tools: string[];
	docker_config: {
		dockerfile: string;
		compose_file: string;
	};
};

export type HFDeploymentBundle = {
	spec: HFTemplateSpec;
	dockerfile: string;
	compose_file: string;
	config_json: string;
	resolved_model_path?: string | null;
	runtime_notes: string[];
};

const request = async (path: string, options: RequestInit = {}) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hf-models${path}`, {
		method: options.method ?? 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(localStorage.token ? { authorization: `Bearer ${localStorage.token}` } : {}),
			...(options.headers ?? {})
		},
		...options
	})
		.then(async (response) => {
			if (!response.ok) {
				throw await response.json();
			}
			return response.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getHFModels = async ({
	query = '',
	sort = 'newest',
	compatibleOnly = true,
	limit = 40
}: {
	query?: string;
	sort?: HFSort;
	compatibleOnly?: boolean;
	limit?: number;
} = {}): Promise<HFModelsResponse> => {
	const params = new URLSearchParams();
	if (query) {
		params.set('q', query);
	}
	params.set('sort', sort);
	params.set('compatible_only', `${compatibleOnly}`);
	params.set('limit', `${limit}`);

	return request(`?${params.toString()}`);
};

export const createHFTemplateSpec = async (body: {
	template: HFTemplate;
	model: string;
	memory: boolean;
	tools: string[];
}): Promise<HFTemplateSpec> => {
	return request('/template-spec', {
		method: 'POST',
		body: JSON.stringify(body)
	});
};

export const createHFDeploymentBundle = async (body: {
	template: HFTemplate;
	model: string;
	memory: boolean;
	tools: string[];
}): Promise<HFDeploymentBundle> => {
	return request('/deployment-bundle', {
		method: 'POST',
		body: JSON.stringify(body)
	});
};
