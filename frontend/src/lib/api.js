import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const KEYS_NS = "sas";
export const keysStore = {
  get openai() { return localStorage.getItem(`${KEYS_NS}.openai_key`) || ""; },
  get llm() { return localStorage.getItem(`${KEYS_NS}.llm_key`) || ""; },
  set(openaiKey, llmKey) {
    if (openaiKey !== undefined) localStorage.setItem(`${KEYS_NS}.openai_key`, openaiKey);
    if (llmKey !== undefined) localStorage.setItem(`${KEYS_NS}.llm_key`, llmKey);
  },
  clear() {
    localStorage.removeItem(`${KEYS_NS}.openai_key`);
    localStorage.removeItem(`${KEYS_NS}.llm_key`);
  },
  has() { return !!(localStorage.getItem(`${KEYS_NS}.openai_key`) && localStorage.getItem(`${KEYS_NS}.llm_key`)); },
};

function authHeaders() {
  return {
    "X-Anthropic-Key": keysStore.llm,
    "X-OpenAI-Key": keysStore.openai,
  };
}

export const api = {
  testAnthropic: () =>
    axios.post(`${API}/keys/test-anthropic`, null, { headers: authHeaders() }),
  testOpenAI: () =>
    axios.post(`${API}/keys/test-openai`, null, { headers: authHeaders() }),

  listBrands: () => axios.get(`${API}/brands`),
  getBrand: (id) => axios.get(`${API}/brands/${id}`),
  createBrand: (data) => axios.post(`${API}/brands`, data),
  deleteBrand: (id) => axios.delete(`${API}/brands/${id}`),
  research: (id) => axios.post(`${API}/brands/${id}/research`, null, { headers: authHeaders() }),
  generate: (id, angle) =>
    axios.post(`${API}/brands/${id}/generate`, { angle }, {
      headers: authHeaders(),
      timeout: 240000,
    }),
  listRuns: (id) => axios.get(`${API}/brands/${id}/runs`),
  downloadZipUrl: (id) => `${API}/brands/${id}/download`,

  listTemplates: () => axios.get(`${API}/templates`),
  patchTemplate: (id, patch) => axios.patch(`${API}/templates/${id}`, patch),
  resetTemplates: () => axios.post(`${API}/templates/reset`),
  createTemplate: (data) => axios.post(`${API}/templates`, data),
  deleteTemplate: (id) => axios.delete(`${API}/templates/${id}`),

  getSettings: () => axios.get(`${API}/settings`),
  patchSettings: (patch) => axios.patch(`${API}/settings`, patch),
};
