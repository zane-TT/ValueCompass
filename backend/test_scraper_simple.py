import sys
sys.path.append('.')

from app.scraper import sync_get_annual_reports

if __name__ == "__main__":
    print("Testing financial report scraper...")
    try:
        # Test with Kweichow Moutai
        print("\n=== Testing with 600519 (贵州茅台) ===")
        result = sync_get_annual_reports("600519")
        print(f"Company: {result.company_name}")
        print(f"Ticker: {result.ticker}")
        print(f"Fetched at: {result.fetched_at}")
        print(f"Total bulletins: {len(result.bulletins)}")
        
        if result.bulletins:
            print("\nRecent bulletins:")
            for i, bulletin in enumerate(result.bulletins[:3]):
                print(f"{i+1}. {bulletin.title}")
                print(f"   Date: {bulletin.publish_date}")
                print(f"   Type: {bulletin.bulletin_type}")
                print(f"   URL: {bulletin.url}")
                print()
        else:
            print("No bulletins found")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()