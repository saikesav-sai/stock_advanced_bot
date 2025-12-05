import csv
import json
import sys


def extract_companies_from_multiple_files(json_files, csv_file):
    """
    Extract unique company names and their trading symbols from multiple JSON files.
    
    Args:
        json_files: List of paths to input JSON files
        csv_file: Path to output CSV file
    """
    try:
        all_companies = {}
        
        for json_file in json_files:
            print(f"\nReading JSON file: {json_file}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if not isinstance(data, list) or len(data) == 0:
                    print(f"Warning: {json_file} is empty or not an array, skipping...")
                    continue
                
                print(f"Found {len(data)} records in {json_file}")
                
                # Extract companies from this file
                for item in data:
                    if isinstance(item, dict):
                        name = item.get('name', '')
                        symbol = item.get('trading_symbol', '')
                        exchange = item.get('exchange', '')
                        
                        # Skip if name or symbol is missing
                        if not name or not symbol:
                            continue
                        
                        # Create a unique key with exchange to differentiate NSE/BSE listings
                        key = (name, symbol, exchange)
                        
                        # Store if not already present
                        if key not in all_companies:
                            all_companies[key] = {
                                'name': name,
                                'trading_symbol': symbol,
                                'exchange': exchange,
                                'isin': item.get('isin', ''),
                                'segment': item.get('segment', ''),
                                'instrument_type': item.get('instrument_type', ''),
                                'short_name': item.get('short_name', '')
                            }
                
            except FileNotFoundError:
                print(f"Warning: File '{json_file}' not found, skipping...")
                continue
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON in '{json_file}' - {e}, skipping...")
                continue
        
        if not all_companies:
            print("\nError: No valid data found in any of the files")
            return False
        
        print(f"\n{'='*80}")
        print(f"Total unique company-symbol-exchange combinations: {len(all_companies)}")
        
        # Convert to list and sort by exchange, then company name
        companies_list = sorted(all_companies.values(), 
                               key=lambda x: (x['exchange'], x['name']))
        
        # Write to CSV
        print(f"Writing to CSV file: {csv_file}")
        fieldnames = ['exchange', 'name', 'trading_symbol', 'short_name', 'isin', 'segment', 'instrument_type']
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(companies_list)
        
        print(f"Successfully extracted {len(companies_list)} unique companies to CSV!")
        
        # Show statistics by exchange
        print("\nStatistics by Exchange:")
        print("-" * 80)
        exchange_counts = {}
        for company in companies_list:
            exchange = company['exchange']
            exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
        
        for exchange, count in sorted(exchange_counts.items()):
            print(f"  {exchange}: {count} entries")
        
        # Show sample entries
        print("\nSample entries:")
        print("-" * 80)
        for i, company in enumerate(companies_list[:10]):
            print(f"{i+1}. [{company['exchange']}] {company['name']} -> {company['trading_symbol']}")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Default files
    input_files = ["BSE.json", "NSE.json"]
    output_file = "companies_combined.csv"
    
    # Check if command line arguments provided
    if len(sys.argv) > 1:
        # If arguments provided, use them as input files
        input_files = sys.argv[1:-1] if len(sys.argv) > 2 else [sys.argv[1]]
        output_file = sys.argv[-1] if len(sys.argv) > 2 else "companies_combined.csv"
    
    print("=" * 80)
    print("Company Name & Symbol Extractor (NSE + BSE)")
    print("=" * 80)
    print(f"Input files: {', '.join(input_files)}")
    print(f"Output file: {output_file}")
    
    success = extract_companies_from_multiple_files(input_files, output_file)
    
    if success:
        print("\n✓ Extraction completed successfully!")
        print(f"  Output file: {output_file}")
    else:
        print("\n✗ Extraction failed!")
        sys.exit(1)
