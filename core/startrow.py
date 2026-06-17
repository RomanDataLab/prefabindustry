#!/usr/bin/env python3
# Start execution of enrichCompanyData.py and enrichCompanyDataGemini.py from row 184
import sys
import argparse
from pathlib import Path

# Fix Windows encoding issues
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Default starting row
DEFAULT_START_ROW = 184

def run_openai_script(start_row: int):
    """Run enrichCompanyData.py (OpenAI version) with start_row parameter"""
    try:
        from enrichCompanyData import process_csv_file
        
        script_dir = Path(__file__).parent
        maps_dir = script_dir.parent / 'maps' / 'public'
        input_csv = maps_dir / 'prefabworldtest_2.csv'
        output_csv = maps_dir / 'prefabworldfin.csv'
        
        if not input_csv.exists():
            print(f"❌ Error: Input file not found: {input_csv}")
            return False
        
        print(f"\n{'='*60}")
        print(f"🚀 Running enrichCompanyData.py (OpenAI) starting from row {start_row}")
        print(f"{'='*60}\n")
        
        process_csv_file(input_csv, output_csv, start_row=start_row)
        
        print(f"\n✅ enrichCompanyData.py completed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Error importing enrichCompanyData: {e}")
        return False
    except Exception as e:
        print(f"❌ Error running enrichCompanyData.py: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_gemini_script(start_row: int):
    """Run enrichCompanyDataGemini.py (Gemini version) with start_row parameter"""
    try:
        from enrichCompanyDataGemini import process_csv_file
        
        script_dir = Path(__file__).parent
        maps_dir = script_dir.parent / 'maps' / 'public'
        input_csv = maps_dir / 'prefabworldtest_2.csv'
        output_csv = maps_dir / 'prefabworldfin.csv'
        
        if not input_csv.exists():
            print(f"❌ Error: Input file not found: {input_csv}")
            return False
        
        print(f"\n{'='*60}")
        print(f"🚀 Running enrichCompanyDataGemini.py (Gemini) starting from row {start_row}")
        print(f"{'='*60}\n")
        
        process_csv_file(input_csv, output_csv, start_row=start_row)
        
        print(f"\n✅ enrichCompanyDataGemini.py completed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Error importing enrichCompanyDataGemini: {e}")
        return False
    except Exception as e:
        print(f"❌ Error running enrichCompanyDataGemini.py: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Run CSV enrichment scripts starting from a specific row',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python startrow.py                    # Run both scripts from row 184 (default)
  python startrow.py --row 200          # Run both scripts from row 200
  python startrow.py --openai --row 184 # Run only OpenAI script from row 184
  python startrow.py --gemini --row 184 # Run only Gemini script from row 184
        """
    )
    parser.add_argument(
        '--row', '-r',
        type=int,
        default=DEFAULT_START_ROW,
        help=f'Starting row number (default: {DEFAULT_START_ROW})'
    )
    parser.add_argument(
        '--openai',
        action='store_true',
        help='Run only enrichCompanyData.py (OpenAI version)'
    )
    parser.add_argument(
        '--gemini',
        action='store_true',
        help='Run only enrichCompanyDataGemini.py (Gemini version)'
    )
    
    args = parser.parse_args()
    
    # Add current directory to path for imports
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    
    start_row = args.row
    
    print(f"\n{'='*60}")
    print(f"📋 CSV Enrichment Scripts - Starting from row {start_row}")
    print(f"{'='*60}\n")
    
    results = {}
    
    # Determine which scripts to run
    run_openai = args.openai or (not args.gemini and not args.openai)
    run_gemini = args.gemini or (not args.gemini and not args.openai)
    
    # Run OpenAI script
    if run_openai:
        results['enrichCompanyData.py (OpenAI)'] = run_openai_script(start_row)
        if not results['enrichCompanyData.py (OpenAI)']:
            print(f"\n⚠️  enrichCompanyData.py failed.\n")
    
    # Run Gemini script
    if run_gemini:
        results['enrichCompanyDataGemini.py (Gemini)'] = run_gemini_script(start_row)
        if not results['enrichCompanyDataGemini.py (Gemini)']:
            print(f"\n⚠️  enrichCompanyDataGemini.py failed.\n")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Execution Summary")
    print(f"{'='*60}")
    for script, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"  {script}: {status}")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
