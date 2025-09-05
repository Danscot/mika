"""
This module is there to crawl websites using Firecrawl
"""

from firecrawl import FirecrawlApp


class Crawler:
    def __init__(self, api_key="", limit=100):

        self.api = api_key

        self.limit = limit
        
        self.client = FirecrawlApp(api_key=self.api)

    def crawler_job(self, url):
        try:
            result = self.client.crawl_url(
                url,
                params={
                    "limit": self.limit,
                    "formats": ["markdown"]
                }
            )

            if not result or "data" not in result:
                print(f"⚠️ No crawl results from {url}")
                return []

            # Extract markdown docs
            return [doc["markdown"] for doc in result["data"] if "markdown" in doc]

        except Exception as e:
            print(f"❌ Error crawling {url}: {e}")
            return []
