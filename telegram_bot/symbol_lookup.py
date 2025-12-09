"""
Symbol Lookup Utility
Provides functions to convert between stock names and ISIN codes
"""
import csv
from pathlib import Path
from typing import Dict, List, Optional


class SymbolLookup:
    def __init__(self):
        self.csv_path = Path(__file__).parent.parent / "bin" / "Final_symbols.csv"
        self.symbol_data: List[Dict[str, str]] = []
        self.load_symbols()
    
    def load_symbols(self):
        """Load symbol data from CSV file"""
        try:
            # Use utf-8-sig to automatically remove BOM if present
            with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                self.symbol_data = list(reader)
        except Exception as e:
            print(f"Error loading symbols CSV: {e}")
            self.symbol_data = []
    
    def get_isin_by_name(self, stock_name: str, exchange: str = None) -> Optional[str]:
        """
        Get ISIN code by stock name
        
        Args:
            stock_name: Name of the stock (case-insensitive)
            exchange: Optional exchange filter (BSE/NSE_EQ)
        
        Returns:
            ISIN code or None if not found
        """
        stock_name = stock_name.strip().upper()
        
        for row in self.symbol_data:
            name = row.get('Name', '').upper()
            trading_symbol = row.get('Trading_symbol', '').upper()
            
            # Match by name or trading symbol
            if stock_name in name or stock_name == trading_symbol:
                if exchange:
                    # Clean exchange name
                    exchange_clean = exchange.replace('_EQ', '').upper()
                    row_exchange = row.get('Exchange', '').upper()
                    
                    if exchange_clean == row_exchange:
                        return row.get('isin')
                else:
                    return row.get('isin')
        
        return None
    
    def get_name_by_isin(self, isin: str) -> Optional[str]:
        """
        Get stock name by ISIN code
        
        Args:
            isin: ISIN code
        
        Returns:
            Stock name or None if not found
        """
        isin = isin.strip().upper()
        
        for row in self.symbol_data:
            if row.get('isin', '').upper() == isin:
                return row.get('Name')
        
        return None
    
    def get_trading_symbol_by_isin(self, isin: str) -> Optional[str]:
        """
        Get trading symbol by ISIN code
        
        Args:
            isin: ISIN code
        
        Returns:
            Trading symbol or None if not found
        """
        isin = isin.strip().upper()
        
        for row in self.symbol_data:
            if row.get('isin', '').upper() == isin:
                return row.get('Trading_symbol')
        
        return None
    
    def search_stocks(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search for stocks by name or trading symbol
        
        Args:
            query: Search query
            limit: Maximum number of results
        
        Returns:
            List of matching stocks with their details
        """
        query = query.strip().upper()
        results = []
        
        for row in self.symbol_data:
            name = row.get('Name', '').upper()
            trading_symbol = row.get('Trading_symbol', '').upper()
            
            if query in name or query in trading_symbol:
                results.append({
                    'exchange': row.get('Exchange'),
                    'name': row.get('Name'),
                    'trading_symbol': row.get('Trading_symbol'),
                    'isin': row.get('isin')
                })
                
                if len(results) >= limit:
                    break
        
        return results
    
    def parse_instrument_key(self, instrument_key: str) -> Optional[Dict[str, str]]:
        """
        Parse instrument key and return details
        
        Args:
            instrument_key: Format "EXCHANGE|ISIN"
        
        Returns:
            Dictionary with exchange, isin, and name
        """
        if '|' not in instrument_key:
            return None
        
        parts = instrument_key.split('|')
        if len(parts) != 2:
            return None
        
        exchange, isin = parts
        name = self.get_name_by_isin(isin)
        trading_symbol = self.get_trading_symbol_by_isin(isin)
        
        return {
            'exchange': exchange,
            'isin': isin,
            'name': name or 'Unknown',
            'trading_symbol': trading_symbol or 'Unknown'
        }
    
    def create_instrument_key(self, stock_name: str, exchange: str) -> Optional[str]:
        """
        Create instrument key from stock name and exchange
        
        Args:
            stock_name: Name of the stock
            exchange: Exchange (BSE_EQ or NSE_EQ)
        
        Returns:
            Instrument key in format "EXCHANGE|ISIN" or None if not found
        """
        isin = self.get_isin_by_name(stock_name, exchange)
        
        if isin:
            return f"{exchange}|{isin}"
        
        return None

# Global instance
_lookup = None

def get_lookup() -> SymbolLookup:
    """Get or create global SymbolLookup instance"""
    global _lookup
    if _lookup is None:
        _lookup = SymbolLookup()
    return _lookup
