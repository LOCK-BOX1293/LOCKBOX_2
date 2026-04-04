import { Beaker, Settings, Database, Shield, Zap } from 'lucide-react';
import clsx from 'clsx';

interface FunctionItem {
  name: string;
  desc: string;
  badges: string[];
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
        {nodeData.functions && nodeData.functions.length > 0 && (
          <>
            <div className="section-label">Functions</div>
            {nodeData.functions.map((fn: FunctionItem, i: number) => (
              <div key={i} className="function-card">
                <div className="function-name">
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--text-primary)' }}></div>
                  {fn.name}()
                </div>
                <div className="function-desc">{fn.desc}</div>
                <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                  {fn.badges.map((b) => (
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
            <div className="section-label">Source</div>
            <pre className="code-block">
              <code>{nodeData.code}</code>
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
             <div className="section-label">Edge Context</div>
             <p style={{fontSize: '0.9rem', color: 'var(--text-muted)'}}>{nodeData.edge_context}</p>
             <pre className="code-block" style={{marginTop: '12px'}}>
               <code>{nodeData.edge_code_snippet}</code>
             </pre>
           </div>
        )}
      </div>
    </div>
  );
}
