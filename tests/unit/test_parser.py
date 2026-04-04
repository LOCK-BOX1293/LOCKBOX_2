from src.parser.ast_parser import ASTParser

def test_python_parsing():
    parser = ASTParser()
    code = """
def my_func():
    pass

class MyClass:
    def method(self):
        pass
"""
    symbols = parser.parse(code, "python")
    
    names = [s.name for s in symbols]
    assert "my_func" in names
    assert "MyClass" in names
    assert "method" in names

    # check boundaries
    method_sym = next(s for s in symbols if s.name == "method")
    assert method_sym.symbol_type == "function"
