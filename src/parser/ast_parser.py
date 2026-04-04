import hashlib
from typing import Any, Dict, List, Optional
import tree_sitter
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript

from src.core.config import logger

class SymbolData:
    def __init__(self, name: str, symbol_type: str, start_line: int, end_line: int, signature: str = ""):
        self.name = name
        self.symbol_type = symbol_type
        self.start_line = start_line
        self.end_line = end_line
        self.signature = signature

class ASTParser:
    def __init__(self):
        try:
            # tree-sitter v0.21 API bindings
            self.lang_python = tree_sitter.Language(tree_sitter_python.language(), "python")
            self.lang_js = tree_sitter.Language(tree_sitter_javascript.language(), "javascript")
            self.lang_ts = tree_sitter.Language(tree_sitter_typescript.language_typescript(), "typescript")
        except Exception as e:
            logger.error(f"Failed to initialize tree-sitter languages: {e}")
            raise

        self.parsers = {
            "python": tree_sitter.Parser(),
            "javascript": tree_sitter.Parser(),
            "typescript": tree_sitter.Parser(),
        }
        self.parsers["python"].set_language(self.lang_python)
        self.parsers["javascript"].set_language(self.lang_js)
        self.parsers["typescript"].set_language(self.lang_ts)

        # Queries
        self.queries = {
            "python": self.lang_python.query("""
                (function_definition
                    name: (identifier) @name
                ) @function
                
                (class_definition
                    name: (identifier) @name
                ) @class
            """),
            "javascript": self.lang_js.query("""
                (function_declaration
                    name: (identifier) @name
                ) @function
                (class_declaration
                    name: (identifier) @name
                ) @class
                (arrow_function) @function
            """),
            "typescript": self.lang_ts.query("""
                (function_declaration
                    name: (identifier) @name
                ) @function
                (class_declaration
                    name: (identifier) @name
                ) @class
            """)
        }

    def parse(self, content: str, language: str) -> List[SymbolData]:
        if language not in self.parsers:
            return []
            
        parser = self.parsers[language]
        tree = parser.parse(bytes(content, "utf8"))
        
        symbols = []
        if language in self.queries:
            query = self.queries[language]
            # Captures is a list of tuples: (node, capture_name)
            captures = query.captures(tree.root_node)
            
            # Simple heuristic matching mechanism
            # We iterate pairs or look forward to match @name inside @class/@function
            idx = 0
            while idx < len(captures):
                node, capture_type = captures[idx]
                
                if capture_type in ("function", "class"):
                    # the next capture might be the name
                    name_str = f"anonymous_{node.start_point[0]}"
                    if idx + 1 < len(captures) and captures[idx+1][1] == "name":
                        name_node = captures[idx+1][0]
                        name_str = content[name_node.start_byte:name_node.end_byte]
                    
                    symbol_type = "function" if capture_type == "function" else "class"
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    
                    # Optional: extract signature from node text
                    signature = ""
                    # If the node has lines, we can get first line
                    node_text = content[node.start_byte:node.end_byte]
                    lines = node_text.splitlines()
                    if lines:
                        signature = lines[0][:100] # trim
                    
                    symbols.append(SymbolData(
                        name=name_str,
                        symbol_type=symbol_type,
                        start_line=start_line,
                        end_line=end_line,
                        signature=signature
                    ))
                idx += 1
                
        return symbols

def hash_id(*args) -> str:
    """Generate a deterministic sha256 hex string given variable arguments"""
    key = "|".join(str(a) for a in args)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
