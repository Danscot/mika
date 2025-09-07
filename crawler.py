"""
This module is there to crawl websites using Firecrawl
"""
from firecrawl import Firecrawl
from firecrawl.types import ScrapeOptions


class Crawler:
    def __init__(self):

        self.limit = 2

        self.client = Firecrawl(api_key='fc-46954301e4ff46e3a6bcc3bf3aafc320')

    def crawler_job(self, url):

        try:

            result = self.client.crawl(

                url,
                
                limit = self.limit,

				scrape_options=ScrapeOptions(formats=['markdown']),

				poll_interval=30
            )

			# Extract the markdown text into a list of documents

            docs = [doc.markdown for doc in crawl_status.data if hasattr(doc, "markdown")]

            return docs

        except Exception as e:

            print(f"❌ Error crawling {url}: {e}")

            return []

