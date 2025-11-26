/**
 * FactCard Component
 * Displays a single fact with edit/delete actions
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Pencil, Trash2, Calendar, Database } from 'lucide-react';
import type { UserFact } from '@/services/memory';

interface FactCardProps {
  fact: UserFact;
  onEdit: (fact: UserFact) => void;
  onDelete: (factId: string) => void;
}

export function FactCard({ fact, onEdit, onDelete }: FactCardProps) {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this fact? This action cannot be undone.')) {
      return;
    }

    setIsDeleting(true);
    try {
      await onDelete(fact.id);
    } finally {
      setIsDeleting(false);
    }
  };

  const importanceColor =
    fact.importance >= 0.8
      ? 'bg-green-500/20 text-green-400 border-green-500/50'
      : fact.importance >= 0.5
      ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50'
      : 'bg-gray-500/20 text-gray-400 border-gray-500/50';

  return (
    <Card className="hover:border-primary/50 transition-colors">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1 flex-1">
            <CardTitle className="text-lg font-semibold">{fact.fact_key}</CardTitle>
            <p className="text-sm text-muted-foreground">{fact.fact_value}</p>
          </div>
          <div className="flex gap-2 ml-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onEdit(fact)}
              title="Edit fact"
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDelete}
              disabled={isDeleting}
              title="Delete fact"
              className="text-destructive hover:text-destructive/80"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex flex-wrap gap-2 text-xs">
          {/* Importance Badge */}
          <Badge variant="outline" className={importanceColor}>
            Importance: {(fact.importance * 100).toFixed(0)}%
          </Badge>

          {/* Agent Badge */}
          {fact.agent_id ? (
            <Badge variant="outline">Agent-Specific</Badge>
          ) : (
            <Badge variant="outline">Global</Badge>
          )}

          {/* Validity Badge */}
          {!fact.is_valid && <Badge variant="destructive">Expired</Badge>}

          {/* Created Date */}
          <Badge variant="secondary" className="gap-1">
            <Calendar className="h-3 w-3" />
            {new Date(fact.created_at).toLocaleDateString()}
          </Badge>

          {/* Embedding Provider */}
          {fact.embedding_provider && (
            <Badge variant="secondary" className="gap-1">
              <Database className="h-3 w-3" />
              {fact.embedding_provider}
            </Badge>
          )}
        </div>

        {/* Optional fact text (natural language) */}
        {fact.fact_text && fact.fact_text !== `${fact.fact_key}: ${fact.fact_value}` && (
          <p className="text-xs text-muted-foreground mt-3 italic">{fact.fact_text}</p>
        )}

        {/* Embedding Model */}
        {fact.embedding_model && (
          <p className="text-xs text-muted-foreground mt-2">
            Model: {fact.embedding_model}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
