/**
 * VoxBridge Knowledge/RAG Service
 * Handles all communication with the voxbridge-rag service for collections and documents
 */

// RAG service runs on port 4910
const RAG_BASE_URL = import.meta.env.PROD
  ? '/rag' // Proxied by nginx in production
  : (import.meta.env.VITE_RAG_URL || 'http://localhost:4910');

// ============================================================================
// Types
// ============================================================================

export interface Collection {
  id: string;
  name: string;
  description: string | null;
  user_id: string;
  is_public: boolean;
  document_count: number;
  chunk_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CollectionCreateRequest {
  name: string;
  description?: string | null;
  is_public?: boolean;
  metadata?: Record<string, unknown>;
}

export interface CollectionUpdateRequest {
  name?: string;
  description?: string | null;
  is_public?: boolean;
  metadata?: Record<string, unknown>;
}

export interface Document {
  id: string;
  collection_id: string;
  filename: string;
  source_type: string;
  source_url: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  content_hash: string | null;
  chunk_count: number;
  processing_status: 'pending' | 'processing' | 'completed' | 'failed';
  processing_error: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DocumentChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  token_count: number | null;
  start_char: number | null;
  end_char: number | null;
  page_number: number | null;
  section_title: string | null;
  metadata: Record<string, unknown>;
  ingested_at: string;
  valid_from: string;
  valid_until: string | null;
}

export interface AgentCollection {
  id: string;
  agent_id: string;
  collection_id: string;
  priority: number;
  created_at: string;
}

export interface AgentCollectionRequest {
  agent_id: string;
  priority?: number;
}

export interface WebScrapeRequest {
  url: string;
  title?: string;
}

export interface SearchRequest {
  query: string;
  collection_ids?: string[];
  agent_id?: string;
  top_k?: number;
  use_reranking?: boolean;
  use_graph?: boolean;
  include_citations?: boolean;
}

export interface SearchResult {
  chunk_id: string;
  content: string;
  score: number;
  document_id: string;
  document_name: string;
  collection_id: string;
  collection_name: string | null;
  chunk_index: number;
  page_number: number | null;
  section_title: string | null;
  vector_score: number;
  bm25_score: number;
  graph_score: number;
}

export interface Citation {
  index: number;
  document_name: string;
  collection_name: string | null;
  page_number: number | null;
  section_title: string | null;
  relevance_score: number;
  excerpt: string;
  chunk_id: string | null;
  document_id: string | null;
}

export interface SearchResponse {
  results: SearchResult[];
  citations: Citation[] | null;
  query: string;
  total_candidates: number;
  retrieval_time_ms: number;
  rerank_time_ms: number;
}

export interface RAGHealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  service: string;
  version: string;
  components: {
    database: boolean;
    neo4j: boolean | null;
    retrieval: boolean;
  };
  config: {
    embedding_model: string;
    reranker_model: string;
    chunk_size: number;
  };
}

// ============================================================================
// API Client
// ============================================================================

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${RAG_BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`RAG API Error: ${response.status} - ${error}`);
  }

  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }

  return response.json();
}

// ============================================================================
// Health
// ============================================================================

export async function getRAGHealth(): Promise<RAGHealthResponse> {
  return request<RAGHealthResponse>('/health');
}

// ============================================================================
// Collections
// ============================================================================

export async function listCollections(userId: string): Promise<Collection[]> {
  return request<Collection[]>(`/api/collections?user_id=${encodeURIComponent(userId)}`);
}

export async function getCollection(collectionId: string): Promise<Collection> {
  return request<Collection>(`/api/collections/${collectionId}`);
}

export async function createCollection(
  userId: string,
  collection: CollectionCreateRequest
): Promise<Collection> {
  return request<Collection>(`/api/collections?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    body: JSON.stringify(collection),
  });
}

export async function updateCollection(
  collectionId: string,
  updates: CollectionUpdateRequest
): Promise<Collection> {
  return request<Collection>(`/api/collections/${collectionId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

export async function deleteCollection(collectionId: string): Promise<void> {
  return request<void>(`/api/collections/${collectionId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Documents
// ============================================================================

export async function listDocuments(collectionId: string): Promise<Document[]> {
  return request<Document[]>(`/api/collections/${collectionId}/documents`);
}

export async function getDocument(
  collectionId: string,
  documentId: string
): Promise<Document> {
  return request<Document>(`/api/collections/${collectionId}/documents/${documentId}`);
}

export async function uploadDocument(
  collectionId: string,
  file: File,
  metadata?: Record<string, unknown>
): Promise<Document> {
  const formData = new FormData();
  formData.append('file', file);
  if (metadata) {
    formData.append('metadata', JSON.stringify(metadata));
  }

  const url = `${RAG_BASE_URL}/api/collections/${collectionId}/documents`;
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
    // Don't set Content-Type header - browser will set it with boundary
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Upload failed: ${response.status} - ${error}`);
  }

  return response.json();
}

export async function scrapeWebPage(
  collectionId: string,
  req: WebScrapeRequest
): Promise<Document> {
  return request<Document>(`/api/collections/${collectionId}/documents/web`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function deleteDocument(
  collectionId: string,
  documentId: string
): Promise<void> {
  return request<void>(`/api/collections/${collectionId}/documents/${documentId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Document Chunks
// ============================================================================

export async function listDocumentChunks(
  collectionId: string,
  documentId: string,
  limit: number = 100,
  offset: number = 0
): Promise<DocumentChunk[]> {
  return request<DocumentChunk[]>(
    `/api/collections/${collectionId}/documents/${documentId}/chunks?limit=${limit}&offset=${offset}`
  );
}

// ============================================================================
// Agent-Collection Linking
// ============================================================================

export async function listLinkedAgents(collectionId: string): Promise<AgentCollection[]> {
  return request<AgentCollection[]>(`/api/collections/${collectionId}/agents`);
}

export async function linkAgentToCollection(
  collectionId: string,
  req: AgentCollectionRequest
): Promise<AgentCollection> {
  return request<AgentCollection>(`/api/collections/${collectionId}/agents`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function unlinkAgentFromCollection(
  collectionId: string,
  agentId: string
): Promise<void> {
  return request<void>(`/api/collections/${collectionId}/agents/${agentId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Search
// ============================================================================

export async function searchKnowledge(req: SearchRequest): Promise<SearchResponse> {
  return request<SearchResponse>('/api/knowledge/search', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function searchAgentKnowledge(
  agentId: string,
  query: string,
  topK: number = 10
): Promise<SearchResponse> {
  return request<SearchResponse>(
    `/api/knowledge/agents/${agentId}/search?query=${encodeURIComponent(query)}&top_k=${topK}`
  );
}

// ============================================================================
// Graph Types
// ============================================================================

export interface GraphNode {
  id: string;
  label: string;
  entity_type: string;
  properties: Record<string, unknown>;
  summary: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface EntitySearchResponse {
  entities: GraphNode[];
  count: number;
}

export interface GraphStatsResponse {
  connected: boolean;
  node_count: number;
  edge_count: number;
  entity_types: Array<{ type: string; count: number }>;
  error?: string;
}

// ============================================================================
// Graph API
// ============================================================================

export async function getGraphStats(): Promise<GraphStatsResponse> {
  return request<GraphStatsResponse>('/api/graph/stats');
}

export async function searchEntities(
  query?: string,
  entityType?: string,
  limit: number = 50
): Promise<EntitySearchResponse> {
  const params = new URLSearchParams();
  if (query) params.append('query', query);
  if (entityType) params.append('entity_type', entityType);
  params.append('limit', limit.toString());

  return request<EntitySearchResponse>(`/api/graph/entities?${params.toString()}`);
}

export async function getSubgraph(
  entityId?: string,
  query?: string,
  depth: number = 2,
  limit: number = 100
): Promise<GraphData> {
  const params = new URLSearchParams();
  if (entityId) params.append('entity_id', entityId);
  if (query) params.append('query', query);
  params.append('depth', depth.toString());
  params.append('limit', limit.toString());

  return request<GraphData>(`/api/graph/subgraph?${params.toString()}`);
}
