#!/usr/bin/env python3
import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Simple-CLI: Enhanced shell wrapper with rich UI, multi-shell completion, and environment detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  simpl-cli                    # Start interactive shell
  simpl-cli --help             # Show this help message
  simpl-cli --version          # Show version information
  simpl-cli --config-reload    # Reload configuration
        """
    )
    
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version information"
    )
    
    parser.add_argument(
        "--config-reload",
        action="store_true",
        help="Reload configuration and exit"
    )
    
    parser.add_argument(
        "--cleanup-memory",
        action="store_true",
        help="Clean up memory and exit"
    )
    
    args = parser.parse_args()
    
    if args.version:
        try:
            from simpl_cli import __version__
            print(f"Simple-CLI version {__version__}")
        except ImportError:
            print("Simple-CLI version 0.0.0")
        return 0
    
    if args.config_reload:
        try:
            from simpl_cli.config import Config
            if Config.reload():
                print("Configuration reloaded successfully")
            else:
                print("Failed to reload configuration")
        except ImportError as e:
            print(f"Error: Could not reload configuration: {e}")
        return 0
    
    if args.cleanup_memory:
        try:
            import gc
            
            # Simple memory cleanup
            before_objects = len(gc.get_objects())
            gc.collect()
            after_objects = len(gc.get_objects())
            
            print(f"Memory cleanup performed")
            print(f"Python objects before: {before_objects}")
            print(f"Python objects after: {after_objects}")
            print(f"Objects freed: {before_objects - after_objects}")
        except Exception as e:
            print(f"Error during memory cleanup: {e}")
        return 0
    
    try:
        package_root = os.path.dirname(os.path.abspath(__file__))
        if package_root not in sys.path:
            sys.path.insert(0, package_root)

        from simpl_cli import app

        if hasattr(app, "main"):
            return app.main()

        print("Error: No main() function found in app.py")
        return 1

    except KeyboardInterrupt:
        print("\nBye!")
        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
