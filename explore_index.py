import logging
from search import WhooshSearchProvider
from whoosh import qparser as whoosh_qparser

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def explore_index():
    """Explore the contents of the Whoosh index."""
    whoosh_provider = WhooshSearchProvider()
    
    # Get all documents in the index
    with whoosh_provider.ix.searcher() as searcher:
        # Get all docs (using a wildcard query)
        query_parser = whoosh_qparser.QueryParser("name", whoosh_provider.ix.schema)
        q = query_parser.parse("*")
        results = searcher.search(q, limit=None)  # No limit to see all docs
        
        print(f"\nTotal places in index: {len(results)}")
        print("\nFirst 10 places:")
        for i, result in enumerate(results[:10]):
            print(f"{i+1}. {result['name']} - {result.get('address', 'No address')}")
        
        # Show some example searches
        test_queries = ["coffee", "restaurant", "sushi", "cafe"]
        print("\nTesting some example searches:")
        for query in test_queries:
            q = query_parser.parse(query)
            results = searcher.search(q, limit=5)
            print(f"\nQuery '{query}' found {len(results)} results:")
            for result in results:
                print(f"- {result['name']}")

if __name__ == "__main__":
    explore_index() 