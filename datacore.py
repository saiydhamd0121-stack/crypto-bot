import asyncio
import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
import csv
import os

# Initialize fake user-agent generator
ua = UserAgent()

def get_advanced_headers():
    return {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

async def fetch_and_parse(session, url):
    headers = get_advanced_headers()
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 200:
                html = await response.text()
                # Parse HTML to extract clean text data automatically
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove unwanted tags like scripts and styles
                for script in soup(["script", "style"]):
                    script.extract()
                    
                clean_text = soup.get_text(separator=' ', strip=True)
                return {'url': url, 'status': 'Success', 'data': clean_text[:500]}
            else:
                return {'url': url, 'status': f'Failed with status {response.status}', 'data': ''}
    except Exception as e:
        return {'url': url, 'status': f'Error: {str(e)}', 'data': ''}

async def main_pipeline(urls):
    print("[*] Starting DataCore Engine (Lightweight Version)...")
    connector = aiohttp.TCPConnector(limit_per_host=5, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_and_parse(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
        
        # Filter out empty results
        valid_results = [res for res in results if res['data'] != '']
        
        # Export directly to CSV using built-in Python module (No Pandas required)
        output_file = "final_client_delivery.csv"
        with open(output_file, mode='w', newline='', encoding='utf-8-sig') as csv_file:
            fieldnames = ['url', 'status', 'data']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in valid_results:
                writer.writerow(row)
                
        print(f"[+] Data successfully processed, cleaned, and exported to {output_file}")

if __name__ == "__main__":
    # Target URLs list (Real Estate Targets)
    test_urls = [
        "https://tyronash.com/",
        "https://realestateagentslondon.co.uk/",
        "https://sothebysrealty.co.uk/",
        "https://www.dexters.co.uk/contact-us/our-offices/london-bridge",
        "https://dolcevita.vip/"
    ] * 2
    
    start_time = time.time()
    asyncio.run(main_pipeline(test_urls))
    print(f"[*] Pipeline execution finished in {round(time.time() - start_time, 2)} seconds.")

