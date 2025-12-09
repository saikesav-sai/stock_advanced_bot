"""
Test script for symbol lookup functionality
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from telegram_bot.symbol_lookup import get_lookup


def test_lookup():
    """Test the symbol lookup functionality"""
    lookup = get_lookup()
    
    print("=" * 60)
    print("Symbol Lookup Test")
    print("=" * 60)
    
    # Test 1: Search for RELIANCE
    print("\n1. Searching for 'RELIANCE':")
    results = lookup.search_stocks("RELIANCE", limit=3)
    for r in results:
        print(f"   {r['name']} ({r['trading_symbol']}) - {r['exchange']} - {r['isin']}")
    
    # Test 2: Get ISIN by name
    print("\n2. Getting ISIN for 'RELIANCE' on NSE_EQ:")
    isin = lookup.get_isin_by_name("RELIANCE", "NSE_EQ")
    print(f"   ISIN: {isin}")
    
    # Test 3: Create instrument key
    print("\n3. Creating instrument key for 'TCS' on NSE_EQ:")
    instrument_key = lookup.create_instrument_key("TCS", "NSE_EQ")
    print(f"   Instrument Key: {instrument_key}")
    
    # Test 4: Parse instrument key
    print("\n4. Parsing instrument key:")
    if instrument_key:
        details = lookup.parse_instrument_key(instrument_key)
        print(f"   Exchange: {details['exchange']}")
        print(f"   ISIN: {details['isin']}")
        print(f"   Name: {details['name']}")
        print(f"   Trading Symbol: {details['trading_symbol']}")
    
    # Test 5: Get name by ISIN
    print("\n5. Getting name by ISIN:")
    if isin:
        name = lookup.get_name_by_isin(isin)
        print(f"   Name: {name}")
    
    # Test 6: Search for partial match
    print("\n6. Searching for 'TATA':")
    results = lookup.search_stocks("TATA", limit=5)
    for r in results:
        print(f"   {r['name']} ({r['trading_symbol']}) - {r['exchange']}")
    
    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    test_lookup()
