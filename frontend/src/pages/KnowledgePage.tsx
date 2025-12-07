/**
 * KnowledgePage Component
 * Manages RAG collections, documents, and agent linking
 */

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  Plus,
  FolderOpen,
  FileText,
  Upload,
  Trash2,
  Link2,
  Search,
  Globe,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Bot,
  ExternalLink,
  Network,
} from 'lucide-react';
import {
  listCollections,
  createCollection,
  deleteCollection,
  listDocuments,
  uploadDocument,
  scrapeWebPage,
  deleteDocument,
  listLinkedAgents,
  linkAgentToCollection,
  unlinkAgentFromCollection,
  searchKnowledge,
  getRAGHealth,
} from '@/services/knowledge';
import type {
  Collection,
  CollectionCreateRequest,
  Document,
  SearchResponse,
} from '@/services/knowledge';
import { api } from '@/services/api';
import { useToastHelpers } from '@/components/ui/toast';
import { useAuth } from '@/contexts/AuthContext';
import { GraphView } from '@/components/GraphView';

// ============================================================================
// Helper Components
// ============================================================================

function StatusBadge({ status }: { status: Document['processing_status'] }) {
  switch (status) {
    case 'completed':
      return (
        <Badge variant="default" className="gap-1 bg-green-600">
          <CheckCircle2 className="h-3 w-3" />
          Ready
        </Badge>
      );
    case 'processing':
      return (
        <Badge variant="secondary" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          Processing
        </Badge>
      );
    case 'pending':
      return (
        <Badge variant="outline" className="gap-1">
          <Clock className="h-3 w-3" />
          Pending
        </Badge>
      );
    case 'failed':
      return (
        <Badge variant="destructive" className="gap-1">
          <AlertCircle className="h-3 w-3" />
          Failed
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// ============================================================================
// Main Component
// ============================================================================

export function KnowledgePage() {
  const queryClient = useQueryClient();
  const toast = useToastHelpers();
  const { user } = useAuth();
  const userId = user?.id || '';

  // State
  const [selectedCollection, setSelectedCollection] = useState<Collection | null>(null);
  const [isCreateCollectionOpen, setIsCreateCollectionOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isWebScrapeOpen, setIsWebScrapeOpen] = useState(false);
  const [isLinkAgentOpen, setIsLinkAgentOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  // Form state
  const [newCollection, setNewCollection] = useState<CollectionCreateRequest>({
    name: '',
    description: '',
    is_public: false,
  });
  const [webScrapeUrl, setWebScrapeUrl] = useState('');
  const [webScrapeTitle, setWebScrapeTitle] = useState('');
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [agentPriority, setAgentPriority] = useState(0);

  // Queries
  const { data: ragHealth } = useQuery({
    queryKey: ['rag-health'],
    queryFn: getRAGHealth,
    refetchInterval: 30000,
  });

  const {
    data: collections,
    isLoading: isLoadingCollections,
    error: collectionsError,
  } = useQuery({
    queryKey: ['collections', userId],
    queryFn: () => listCollections(userId),
    enabled: !!userId,
  });

  const { data: documents, isLoading: isLoadingDocuments } = useQuery({
    queryKey: ['documents', selectedCollection?.id],
    queryFn: () => listDocuments(selectedCollection!.id),
    enabled: !!selectedCollection,
  });

  const { data: linkedAgents } = useQuery({
    queryKey: ['linked-agents', selectedCollection?.id],
    queryFn: () => listLinkedAgents(selectedCollection!.id),
    enabled: !!selectedCollection,
  });

  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.getAgents(),
  });

  // Mutations
  const createCollectionMutation = useMutation({
    mutationFn: (req: CollectionCreateRequest) => createCollection(userId, req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collections', userId] });
      setIsCreateCollectionOpen(false);
      setNewCollection({ name: '', description: '', is_public: false });
      toast.success('Collection Created', 'Your new collection is ready');
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  const deleteCollectionMutation = useMutation({
    mutationFn: deleteCollection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collections', userId] });
      setSelectedCollection(null);
      toast.success('Collection Deleted', 'Collection and all documents removed');
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  const uploadDocumentMutation = useMutation({
    mutationFn: ({ file }: { file: File }) =>
      uploadDocument(selectedCollection!.id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', selectedCollection?.id] });
      queryClient.invalidateQueries({ queryKey: ['collections', userId] });
      setIsUploadOpen(false);
      toast.success('Document Uploaded', 'Processing in background...');
    },
    onError: (error: Error) => {
      toast.error('Upload Failed', error.message);
    },
  });

  const webScrapeMutation = useMutation({
    mutationFn: () =>
      scrapeWebPage(selectedCollection!.id, {
        url: webScrapeUrl,
        title: webScrapeTitle || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', selectedCollection?.id] });
      queryClient.invalidateQueries({ queryKey: ['collections', userId] });
      setIsWebScrapeOpen(false);
      setWebScrapeUrl('');
      setWebScrapeTitle('');
      toast.success('Web Page Queued', 'Scraping and processing...');
    },
    onError: (error: Error) => {
      toast.error('Scrape Failed', error.message);
    },
  });

  const deleteDocumentMutation = useMutation({
    mutationFn: (documentId: string) =>
      deleteDocument(selectedCollection!.id, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', selectedCollection?.id] });
      queryClient.invalidateQueries({ queryKey: ['collections', userId] });
      toast.success('Document Deleted', 'Document and chunks removed');
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  const linkAgentMutation = useMutation({
    mutationFn: () =>
      linkAgentToCollection(selectedCollection!.id, {
        agent_id: selectedAgentId,
        priority: agentPriority,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['linked-agents', selectedCollection?.id] });
      setIsLinkAgentOpen(false);
      setSelectedAgentId('');
      setAgentPriority(0);
      toast.success('Agent Linked', 'Agent can now access this collection');
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  const unlinkAgentMutation = useMutation({
    mutationFn: (agentId: string) =>
      unlinkAgentFromCollection(selectedCollection!.id, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['linked-agents', selectedCollection?.id] });
      toast.success('Agent Unlinked', 'Agent no longer has access');
    },
    onError: (error: Error) => {
      toast.error('Error', error.message);
    },
  });

  // Handlers
  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadDocumentMutation.mutate({ file });
    }
  }, [uploadDocumentMutation]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    try {
      const results = await searchKnowledge({
        query: searchQuery,
        collection_ids: selectedCollection ? [selectedCollection.id] : undefined,
        top_k: 10,
        use_reranking: true,
        include_citations: true,
      });
      setSearchResults(results);
    } catch (error) {
      toast.error('Search Failed', (error as Error).message);
    } finally {
      setIsSearching(false);
    }
  };

  // Get agent name by ID
  const getAgentName = (agentId: string) => {
    return agents?.find(a => a.id === agentId)?.name || 'Unknown Agent';
  };

  // Filter out already linked agents
  const availableAgents = agents?.filter(
    a => !linkedAgents?.some(la => la.agent_id === a.id)
  );

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Knowledge Base</h1>
          <p className="text-muted-foreground mt-1">
            Manage document collections for RAG retrieval
          </p>
        </div>
        <div className="flex items-center gap-2">
          {ragHealth && (
            <Badge variant={ragHealth.status === 'healthy' ? 'default' : 'destructive'}>
              {ragHealth.status === 'healthy' ? (
                <CheckCircle2 className="h-3 w-3 mr-1" />
              ) : (
                <AlertCircle className="h-3 w-3 mr-1" />
              )}
              RAG {ragHealth.status}
            </Badge>
          )}
          <Button onClick={() => setIsCreateCollectionOpen(true)} className="gap-2">
            <Plus className="h-4 w-4" />
            New Collection
          </Button>
        </div>
      </div>

      {/* Main Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Collections List */}
        <div className="lg:col-span-1 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FolderOpen className="h-5 w-5" />
                Collections
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {isLoadingCollections && (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin" />
                </div>
              )}

              {collectionsError && (
                <p className="text-destructive text-sm">
                  {(collectionsError as Error).message}
                </p>
              )}

              {collections?.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <FolderOpen className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>No collections yet</p>
                  <p className="text-sm">Create one to get started</p>
                </div>
              )}

              {collections?.map((collection) => (
                <div
                  key={collection.id}
                  onClick={() => setSelectedCollection(collection)}
                  className={`p-3 rounded-lg cursor-pointer transition-colors ${
                    selectedCollection?.id === collection.id
                      ? 'bg-primary/10 border border-primary'
                      : 'bg-muted/50 hover:bg-muted'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{collection.name}</span>
                    {collection.is_public && (
                      <Globe className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                  <div className="flex gap-2 mt-1 text-xs text-muted-foreground">
                    <span>{collection.document_count} docs</span>
                    <span>{collection.chunk_count} chunks</span>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Collection Details */}
        <div className="lg:col-span-2 space-y-4">
          {!selectedCollection ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <FolderOpen className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <p className="text-lg">Select a collection to view details</p>
                <p className="text-sm">Or create a new collection to get started</p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Collection Header */}
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-xl">{selectedCollection.name}</CardTitle>
                      <CardDescription>
                        {selectedCollection.description || 'No description'}
                      </CardDescription>
                    </div>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => {
                        if (confirm('Delete this collection and all its documents?')) {
                          deleteCollectionMutation.mutate(selectedCollection.id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                      <div className="text-2xl font-bold">{selectedCollection.document_count}</div>
                      <div className="text-xs text-muted-foreground">Documents</div>
                    </div>
                    <div>
                      <div className="text-2xl font-bold">{selectedCollection.chunk_count}</div>
                      <div className="text-xs text-muted-foreground">Chunks</div>
                    </div>
                    <div>
                      <div className="text-2xl font-bold">{linkedAgents?.length || 0}</div>
                      <div className="text-xs text-muted-foreground">Linked Agents</div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Tabs */}
              <Tabs defaultValue="documents">
                <TabsList className="w-full">
                  <TabsTrigger value="documents" className="flex-1">
                    <FileText className="h-4 w-4 mr-2" />
                    Documents
                  </TabsTrigger>
                  <TabsTrigger value="agents" className="flex-1">
                    <Bot className="h-4 w-4 mr-2" />
                    Linked Agents
                  </TabsTrigger>
                  <TabsTrigger value="search" className="flex-1">
                    <Search className="h-4 w-4 mr-2" />
                    Search
                  </TabsTrigger>
                  <TabsTrigger value="graph" className="flex-1">
                    <Network className="h-4 w-4 mr-2" />
                    Graph
                  </TabsTrigger>
                </TabsList>

                {/* Documents Tab */}
                <TabsContent value="documents" className="space-y-4">
                  <div className="flex gap-2">
                    <Button onClick={() => setIsUploadOpen(true)} className="gap-2">
                      <Upload className="h-4 w-4" />
                      Upload File
                    </Button>
                    <Button variant="outline" onClick={() => setIsWebScrapeOpen(true)} className="gap-2">
                      <Globe className="h-4 w-4" />
                      Scrape URL
                    </Button>
                  </div>

                  {isLoadingDocuments ? (
                    <div className="flex items-center justify-center py-8">
                      <RefreshCw className="h-6 w-6 animate-spin" />
                    </div>
                  ) : documents?.length === 0 ? (
                    <Card>
                      <CardContent className="py-8 text-center text-muted-foreground">
                        <FileText className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p>No documents yet</p>
                        <p className="text-sm">Upload files or scrape web pages</p>
                      </CardContent>
                    </Card>
                  ) : (
                    <div className="space-y-2">
                      {documents?.map((doc) => (
                        <Card key={doc.id}>
                          <CardContent className="py-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <FileText className="h-5 w-5 text-muted-foreground" />
                                <div>
                                  <div className="font-medium">{doc.filename}</div>
                                  <div className="flex gap-2 text-xs text-muted-foreground">
                                    <span>{doc.source_type}</span>
                                    <span>{formatBytes(doc.file_size_bytes)}</span>
                                    <span>{doc.chunk_count} chunks</span>
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <StatusBadge status={doc.processing_status} />
                                {doc.source_url && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    asChild
                                  >
                                    <a href={doc.source_url} target="_blank" rel="noopener noreferrer">
                                      <ExternalLink className="h-4 w-4" />
                                    </a>
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    if (confirm('Delete this document?')) {
                                      deleteDocumentMutation.mutate(doc.id);
                                    }
                                  }}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </div>
                            {doc.processing_error && (
                              <p className="text-sm text-destructive mt-2">
                                {doc.processing_error}
                              </p>
                            )}
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Agents Tab */}
                <TabsContent value="agents" className="space-y-4">
                  <Button onClick={() => setIsLinkAgentOpen(true)} className="gap-2">
                    <Link2 className="h-4 w-4" />
                    Link Agent
                  </Button>

                  {linkedAgents?.length === 0 ? (
                    <Card>
                      <CardContent className="py-8 text-center text-muted-foreground">
                        <Bot className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p>No agents linked</p>
                        <p className="text-sm">Link agents to give them access to this knowledge</p>
                      </CardContent>
                    </Card>
                  ) : (
                    <div className="space-y-2">
                      {linkedAgents?.map((link) => (
                        <Card key={link.id}>
                          <CardContent className="py-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <Bot className="h-5 w-5 text-muted-foreground" />
                                <div>
                                  <div className="font-medium">{getAgentName(link.agent_id)}</div>
                                  <div className="text-xs text-muted-foreground">
                                    Priority: {link.priority}
                                  </div>
                                </div>
                              </div>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  if (confirm('Unlink this agent?')) {
                                    unlinkAgentMutation.mutate(link.agent_id);
                                  }
                                }}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Search Tab */}
                <TabsContent value="search" className="space-y-4">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Search this collection..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    />
                    <Button onClick={handleSearch} disabled={isSearching}>
                      {isSearching ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Search className="h-4 w-4" />
                      )}
                    </Button>
                  </div>

                  {searchResults && (
                    <div className="space-y-2">
                      <div className="text-sm text-muted-foreground">
                        {searchResults.total_candidates} candidates, {searchResults.results.length} results
                        ({searchResults.retrieval_time_ms.toFixed(0)}ms retrieval, {searchResults.rerank_time_ms.toFixed(0)}ms rerank)
                      </div>
                      {searchResults.results.map((result, i) => (
                        <Card key={result.chunk_id}>
                          <CardContent className="py-3">
                            <div className="flex items-start gap-2">
                              <Badge variant="outline" className="shrink-0">
                                {i + 1}
                              </Badge>
                              <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium">
                                  {result.document_name}
                                  {result.page_number && ` (p.${result.page_number})`}
                                </div>
                                <p className="text-sm text-muted-foreground line-clamp-3 mt-1">
                                  {result.content}
                                </p>
                                <div className="flex gap-2 mt-2 text-xs text-muted-foreground">
                                  <span>Score: {result.score.toFixed(3)}</span>
                                  <span>Vector: {result.vector_score.toFixed(3)}</span>
                                  <span>BM25: {result.bm25_score.toFixed(3)}</span>
                                </div>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Graph Tab */}
                <TabsContent value="graph" className="space-y-4">
                  <GraphView />
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      </div>

      {/* Create Collection Dialog */}
      <Dialog open={isCreateCollectionOpen} onOpenChange={setIsCreateCollectionOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Collection</DialogTitle>
            <DialogDescription>
              Create a new knowledge collection for your documents
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="collection-name">Name *</Label>
              <Input
                id="collection-name"
                placeholder="My Knowledge Base"
                value={newCollection.name}
                onChange={(e) => setNewCollection({ ...newCollection, name: e.target.value })}
              />
            </div>

            <div>
              <Label htmlFor="collection-desc">Description</Label>
              <Textarea
                id="collection-desc"
                placeholder="What this collection is about..."
                value={newCollection.description || ''}
                onChange={(e) => setNewCollection({ ...newCollection, description: e.target.value })}
              />
            </div>

            <div className="flex items-center gap-2">
              <Switch
                id="collection-public"
                checked={newCollection.is_public}
                onCheckedChange={(checked) => setNewCollection({ ...newCollection, is_public: checked })}
              />
              <Label htmlFor="collection-public">Public (visible to all agents)</Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateCollectionOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => createCollectionMutation.mutate(newCollection)}
              disabled={!newCollection.name || createCollectionMutation.isPending}
            >
              {createCollectionMutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Dialog */}
      <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>
              Upload a document to {selectedCollection?.name}
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <Label htmlFor="file-upload">Select File</Label>
            <Input
              id="file-upload"
              type="file"
              accept=".pdf,.docx,.doc,.txt,.md,.py,.js,.ts,.json,.yaml,.yml"
              onChange={handleFileUpload}
              disabled={uploadDocumentMutation.isPending}
            />
            <p className="text-xs text-muted-foreground mt-2">
              Supported: PDF, DOCX, TXT, MD, and common code files (max 50MB)
            </p>
            {uploadDocumentMutation.isPending && (
              <Progress className="mt-4" value={undefined} />
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsUploadOpen(false)}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Web Scrape Dialog */}
      <Dialog open={isWebScrapeOpen} onOpenChange={setIsWebScrapeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Scrape Web Page</DialogTitle>
            <DialogDescription>
              Add a web page to {selectedCollection?.name}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="scrape-url">URL *</Label>
              <Input
                id="scrape-url"
                type="url"
                placeholder="https://example.com/article"
                value={webScrapeUrl}
                onChange={(e) => setWebScrapeUrl(e.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="scrape-title">Title (optional)</Label>
              <Input
                id="scrape-title"
                placeholder="Override document title"
                value={webScrapeTitle}
                onChange={(e) => setWebScrapeTitle(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsWebScrapeOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => webScrapeMutation.mutate()}
              disabled={!webScrapeUrl || webScrapeMutation.isPending}
            >
              {webScrapeMutation.isPending ? 'Scraping...' : 'Scrape'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Link Agent Dialog */}
      <Dialog open={isLinkAgentOpen} onOpenChange={setIsLinkAgentOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link Agent</DialogTitle>
            <DialogDescription>
              Give an agent access to {selectedCollection?.name}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="link-agent">Agent</Label>
              <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                <SelectTrigger id="link-agent">
                  <SelectValue placeholder="Select an agent" />
                </SelectTrigger>
                <SelectContent>
                  {availableAgents?.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {availableAgents?.length === 0 && (
                <p className="text-xs text-muted-foreground mt-1">
                  All agents are already linked
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="link-priority">Priority (higher = more relevant)</Label>
              <Input
                id="link-priority"
                type="number"
                min={0}
                max={100}
                value={agentPriority}
                onChange={(e) => setAgentPriority(parseInt(e.target.value) || 0)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsLinkAgentOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => linkAgentMutation.mutate()}
              disabled={!selectedAgentId || linkAgentMutation.isPending}
            >
              {linkAgentMutation.isPending ? 'Linking...' : 'Link Agent'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
