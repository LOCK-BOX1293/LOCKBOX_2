
import { Search, Hexagon } from 'lucide-react';
import clsx from 'clsx';

interface ToolbarProps {
  mode: 'full' | 'focused';
  setMode: (mode: 'full' | 'focused') => void;
  query: string;
  setQuery: (q: string) => void;
  role: 'backend' | 'frontend' | 'security' | 'architect' | 'debugger';
  setRole: (role: 'backend' | 'frontend' | 'security' | 'architect' | 'debugger') => void;
  onSearch: () => void;
}

export function Toolbar({ mode, setMode, query, setQuery, role, setRole, onSearch }: ToolbarProps) {
  return (
    <div className="toolbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <Hexagon color="#ff8a00" />
        <div className="toolbar-brand">Hackbite Graph</div>
      </div>
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ display: 'flex', background: 'var(--bg-base)', borderRadius: '8px', padding: '4px', border: '1px solid var(--border-color)' }}>
          <button 
            className={clsx('nav-button', { active: mode === 'full' })} 
            style={{ border: 'none', background: mode === 'full' ? 'var(--text-primary)' : 'transparent' }}
            onClick={() => setMode('full')}
          >
            Full Graph
          </button>
          <button 
            className={clsx('nav-button', { active: mode === 'focused' })}
            style={{ border: 'none', background: mode === 'focused' ? 'var(--text-primary)' : 'transparent' }}
            onClick={() => setMode('focused')}
          >
            Focused
          </button>
        </div>

        <div style={{ position: 'relative' }}>
          <Search size={18} style={{ position: 'absolute', left: '12px', top: '10px', color: 'var(--text-muted)' }} />
          <input 
            className="search-input" 
            placeholder="Search symbols or ask AI..." 
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') onSearch(); }}
          />
        </div>

        <select
          value={role}
          onChange={(e) => setRole(e.target.value as any)}
          style={{
            background: 'var(--bg-base)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            padding: '10px 12px'
          }}
        >
          <option value="backend">backend</option>
          <option value="frontend">frontend</option>
          <option value="security">security</option>
          <option value="architect">architect</option>
          <option value="debugger">debugger</option>
        </select>

        <button className="nav-button active" onClick={onSearch}>
          Ask
        </button>
      </div>
    </div>
  );
}
