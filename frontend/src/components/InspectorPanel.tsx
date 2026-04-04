import { Beaker, Settings, Database, Shield, Zap, Link2, FileCode2 } from 'lucide-react';
import clsx from 'clsx';

interface FunctionItem {
  name: string;
  desc?: string;
  badges?: string[];
  symbol_type?: string;
  signature?: string;
  start_line?: number;
  end_line?: number;
  tags?: string[];
}

interface InspectorPanelProps {
  nodeId: string | null;
  nodeData: any;
  onClose: () => void;
}

export function InspectorPanel({ nodeId, nodeData, onClose }: InspectorPanelProps) {
  if (!nodeId || !nodeData) {
    return null;
  }

  // Example mappings for icons based on text
  const getIcon = (badge: string) => {
    switch (badge.toLowerCase()) {
      case 'router': return <Zap size={14} />;
      case 'critical': return <Shield size={14} />;
      case 'config': return <Settings size={14} />;
      case 'database': return <Database size={14} />;
      default: return <Beaker size={14} />;
    }
  };

  const trimCode = (code: string | undefined, maxLines = 120) => {
    if (!code) return '';
    const lines = code.split('\n');
    if (lines.length <= maxLines) return code;
    return `${lines.slice(0, maxLines).join('\n')}\n\n... (${lines.length - maxLines} more lines hidden)`;
  };

  const noteSummary = nodeData?.note_summary || nodeData?.summary || null;
  const queryStructure = nodeData?.query_structure || nodeData?.structure || null;

  return (
    <div className="inspector-panel glass-panel">
      <div className="inspector-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h2 className="inspector-title">{nodeData.title || nodeId}</h2>
            <div className="inspector-subtitle">{nodeData.file_path || 'Unknown path'}</div>
          </div>
          <button className="nav-button" style={{ padding: '6px' }} onClick={onClose}>✕</button>
        </div>
      </div>
      
      <div className="inspector-content">
        {noteSummary && (
          <>
            <div className="section-label">Query Note</div>
            <div className="key-point" style={{ marginBottom: 12 }}>
              <div className="key-point-bullet">◆</div>
              <div>{noteSummary}</div>
            </div>
          </>
        )}

        {queryStructure && (
          <>
            <div className="section-label">Structure</div>
            <pre className="code-block"><code>{typeof queryStructure === 'string' ? queryStructure : JSON.stringify(queryStructure, null, 2)}</code></pre>
          </>
        )}

        {nodeData.functions && nodeData.functions.length > 0 && (
          <>
            <div className="section-label">Functions</div>
            {nodeData.functions.map((fn: FunctionItem, i: number) => (
              <div key={i} className="function-card">
                <div className="function-name">
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--text-primary)' }}></div>
                  {fn.name}{fn.symbol_type === 'class' ? '' : '()'}
                </div>
                {fn.signature && <div className="function-desc" style={{ fontFamily: 'monospace' }}>{fn.signature}</div>}
                {fn.start_line && fn.end_line && (
                  <div className="function-desc">lines: {fn.start_line}-{fn.end_line}</div>
                )}
                {fn.desc && <div className="function-desc">{fn.desc}</div>}
                <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                  {(fn.badges || fn.tags || []).map((b) => (
                    <span 
                      key={b} 
                      className={clsx('function-badge', { 'critical': b.toLowerCase() === 'critical' })}
                      style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                    >
                      {getIcon(b)} {b}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}

        {nodeData.code && (
          <div style={{ marginTop: '24px' }}>
            <div className="section-label"><FileCode2 size={14} style={{ display: 'inline', marginRight: 6 }} />Source (trimmed)</div>
            <pre className="code-block">
              <code>{trimCode(nodeData.code, 100)}</code>
            </pre>
          </div>
        )}

        {nodeData.key_points && nodeData.key_points.length > 0 && (
          <>
            <div className="section-label">Key Points</div>
            {nodeData.key_points.map((pt: string, i: number) => (
              <div key={i} className="key-point">
                <div className="key-point-bullet">◆</div>
                <div>{pt}</div>
              </div>
            ))}
          </>
        )}
        
        {/* If node is an edge context, show that instead */}
        {nodeData.edge_context && (
           <div style={{ marginTop: '24px' }}>
             <div className="section-label"><Link2 size={14} style={{ display: 'inline', marginRight: 6 }} />Connection Context</div>
             <p style={{fontSize: '0.9rem', color: 'var(--text-muted)'}}>{nodeData.edge_context}</p>
             <pre className="code-block" style={{marginTop: '12px'}}>
               <code>{trimCode(nodeData.edge_code_snippet, 80)}</code>
             </pre>
            </div>
        )}

        {nodeData.edge && (
          <div style={{ marginTop: 12 }}>
            <div className="section-label">Connection Metadata</div>
            <pre className="code-block"><code>{JSON.stringify(nodeData.edge, null, 2)}</code></pre>
          </div>
        )}

        {nodeData.from && nodeData.to && (
          <div style={{ marginTop: 12 }}>
            <div className="section-label">From ↔ To Snippets</div>
            <pre className="code-block"><code>{`FROM: ${nodeData.from.file_path || nodeData.from.symbol_id || 'n/a'}\n${trimCode(nodeData.from.code, 30)}\n\nTO: ${nodeData.to.file_path || nodeData.to.symbol_id || 'n/a'}\n${trimCode(nodeData.to.code, 30)}`}</code></pre>
          </div>
        )}
      </div>
    </div>
  );
}
