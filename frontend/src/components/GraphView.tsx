/**
 * GraphView Component
 * Interactive knowledge graph visualization using React Flow
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import ReactFlow, {
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
  BackgroundVariant,
} from 'reactflow';
import type { Node, Edge, NodeMouseHandler } from 'reactflow';
import 'reactflow/dist/style.css';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Search,
  RefreshCw,
  Network,
  AlertCircle,
  Loader2,
  X,
} from 'lucide-react';
import {
  getGraphStats,
  getSubgraph,
  searchEntities,
  type GraphNode as APIGraphNode,
  type GraphData,
  type GraphStatsResponse,
} from '@/services/knowledge';

// ============================================================================
// Types
// ============================================================================

interface EntityDetailsProps {
  entity: APIGraphNode | null;
  onClose: () => void;
}

// Color mapping for entity types
const entityTypeColors: Record<string, string> = {
  Person: '#3b82f6', // blue
  Organization: '#8b5cf6', // purple
  Location: '#10b981', // green
  Event: '#f59e0b', // amber
  Concept: '#ec4899', // pink
  Technology: '#06b6d4', // cyan
  Product: '#f97316', // orange
  Date: '#84cc16', // lime
  Entity: '#6b7280', // gray (default)
};

function getEntityColor(entityType: string): string {
  return entityTypeColors[entityType] || entityTypeColors.Entity;
}

// ============================================================================
// Entity Details Panel
// ============================================================================

function EntityDetails({ entity, onClose }: EntityDetailsProps) {
  if (!entity) return null;

  return (
    <Card className="absolute top-4 right-4 w-80 z-10 shadow-lg">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{entity.label}</CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <Badge
          style={{ backgroundColor: getEntityColor(entity.entity_type) }}
          className="w-fit"
        >
          {entity.entity_type}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-2">
        {entity.summary && (
          <p className="text-sm text-muted-foreground">{entity.summary}</p>
        )}
        {Object.entries(entity.properties).length > 0 && (
          <div className="text-xs space-y-1">
            <div className="font-medium">Properties:</div>
            {Object.entries(entity.properties).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span className="text-muted-foreground">{key}:</span>
                <span>{String(value)}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Graph View Component
// ============================================================================

export function GraphView() {
  // State
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [stats, setStats] = useState<GraphStatsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEntity, setSelectedEntity] = useState<APIGraphNode | null>(null);

  // Convert API data to React Flow format
  const convertToFlowData = useCallback((data: GraphData): { nodes: Node[]; edges: Edge[] } => {
    // Auto-layout nodes in a circular pattern
    const nodeCount = data.nodes.length;
    const radius = Math.max(300, nodeCount * 30);
    const centerX = 400;
    const centerY = 300;

    const flowNodes: Node[] = data.nodes.map((node, index) => {
      const angle = (2 * Math.PI * index) / nodeCount;
      return {
        id: node.id,
        position: {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
        },
        data: {
          label: node.label,
          entityType: node.entity_type,
          summary: node.summary,
          properties: node.properties,
        },
        style: {
          background: getEntityColor(node.entity_type),
          color: 'white',
          borderRadius: 8,
          padding: '8px 12px',
          fontSize: '12px',
          fontWeight: 500,
          minWidth: 80,
          textAlign: 'center' as const,
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });

    const flowEdges: Edge[] = data.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#94a3b8',
      },
      labelStyle: {
        fontSize: 10,
        fill: '#64748b',
        fontWeight: 500,
      },
      labelBgStyle: {
        fill: '#f8fafc',
        fillOpacity: 0.9,
      },
    }));

    return { nodes: flowNodes, edges: flowEdges };
  }, []);

  // Load graph stats
  useEffect(() => {
    async function loadStats() {
      try {
        const statsData = await getGraphStats();
        setStats(statsData);
      } catch (err) {
        console.error('Failed to load graph stats:', err);
      }
    }
    loadStats();
  }, []);

  // Load initial graph data
  const loadGraph = useCallback(async (entityId?: string, query?: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const data = await getSubgraph(entityId, query, 2, 100);
      const { nodes: flowNodes, edges: flowEdges } = convertToFlowData(data);
      setNodes(flowNodes);
      setEdges(flowEdges);
    } catch (err) {
      setError((err as Error).message);
      setNodes([]);
      setEdges([]);
    } finally {
      setIsLoading(false);
    }
  }, [convertToFlowData, setNodes, setEdges]);

  // Initial load
  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Handle node click
  const onNodeClick: NodeMouseHandler = useCallback((_event: React.MouseEvent, node: Node) => {
    const apiNode: APIGraphNode = {
      id: node.id,
      label: node.data.label as string,
      entity_type: node.data.entityType as string,
      summary: node.data.summary as string | null,
      properties: node.data.properties as Record<string, unknown>,
    };
    setSelectedEntity(apiNode);
  }, []);

  // Handle double-click to explore
  const onNodeDoubleClick: NodeMouseHandler = useCallback((_event: React.MouseEvent, node: Node) => {
    loadGraph(node.id);
  }, [loadGraph]);

  // Handle search
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      loadGraph();
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const results = await searchEntities(searchQuery, undefined, 20);
      if (results.entities.length > 0) {
        // Load subgraph centered on first result
        loadGraph(results.entities[0].id);
      } else {
        setNodes([]);
        setEdges([]);
        setError('No entities found matching your search');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, loadGraph, setNodes, setEdges]);

  // Entity type legend
  const entityTypeLegend = useMemo(() => {
    const types = stats?.entity_types || [];
    return types.slice(0, 8); // Show top 8 types
  }, [stats]);

  return (
    <Card className="h-[600px] relative">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Network className="h-5 w-5" />
            <CardTitle>Knowledge Graph</CardTitle>
            {stats && (
              <Badge variant="outline" className="ml-2">
                {stats.node_count} entities, {stats.edge_count} relationships
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              <Input
                placeholder="Search entities..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="w-48 h-8"
              />
              <Button size="sm" variant="outline" onClick={handleSearch}>
                <Search className="h-4 w-4" />
              </Button>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setSearchQuery('');
                loadGraph();
              }}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0 h-[520px] relative">
        {isLoading && (
          <div className="absolute inset-0 bg-background/80 flex items-center justify-center z-20">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <AlertCircle className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>{error}</p>
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => loadGraph()}
              >
                Try Again
              </Button>
            </div>
          </div>
        )}

        {!error && nodes.length === 0 && !isLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <Network className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No entities in the graph yet</p>
              <p className="text-sm">Upload documents to extract entities</p>
            </div>
          </div>
        )}

        {nodes.length > 0 && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            attributionPosition="bottom-left"
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(node: Node) => getEntityColor(node.data?.entityType as string || 'Entity')}
              maskColor="rgba(0, 0, 0, 0.1)"
              style={{ background: '#f8fafc' }}
            />
          </ReactFlow>
        )}

        {/* Entity Details Panel */}
        <EntityDetails
          entity={selectedEntity}
          onClose={() => setSelectedEntity(null)}
        />

        {/* Legend */}
        {entityTypeLegend.length > 0 && (
          <div className="absolute bottom-4 left-4 bg-background/90 p-2 rounded-lg shadow-sm border z-10">
            <div className="text-xs font-medium mb-1">Entity Types</div>
            <div className="flex flex-wrap gap-1">
              {entityTypeLegend.map(({ type, count }) => (
                <Badge
                  key={type}
                  variant="outline"
                  className="text-xs"
                  style={{ borderColor: getEntityColor(type) }}
                >
                  <span
                    className="w-2 h-2 rounded-full mr-1"
                    style={{ backgroundColor: getEntityColor(type) }}
                  />
                  {type} ({count})
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
