import sys
import traceback

def run():
    try:
        from src.cli.main import app
        import typer.core
        # Force typer to not catch exceptions
        sys.argv = ['main', 'index', 'full', '--help']
        app()
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    run()
