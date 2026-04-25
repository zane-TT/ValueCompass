from app.scraper import sync_get_annual_reports

if __name__ == "__main__":
    print("Testing financial report scraper...")
    try:
        result = sync_get_annual_reports("600519")
        print(f"Company: {result.company_name}")
        print(f"Ticker: {result.ticker}")
        print(f"Fetched at: {result.fetched_at}")
        print(f"Total bulletins: {len(result.bulletins)}")
        
        print("\nTop 5 bulletins:")
        for i, bulletin in enumerate(result.bulletins[:5]):
            print(f"{i+1}. {bulletin.title}")
            print(f"   Date: {bulletin.publish_date}")
            print(f"   URL: {bulletin.url}")
            print(f"   Type: {bulletin.bulletin_type}")
            print()
    except Exception as e:
        print(f"Error: {e}")