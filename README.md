# Mesa Backend

A backend service that integrates multiple search providers (Whoosh, Mapbox, Google Places) for iOS app place searches.

## Features

- Multiple search provider integration:
  - Whoosh for local searches
  - Mapbox for geocoding
  - Google Places API for place details
- Caching system for search results
- Firestore integration for place storage
- Search orchestration to combine results from multiple providers

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables:
   - Create a `.env` file with your API keys:
     ```
     MAPBOX_ACCESS_TOKEN=your_mapbox_token
     GOOGLE_PLACES_API_KEY=your_google_places_key
     ```
   - Set up Firebase credentials:
     - Place your Firebase Admin SDK service account JSON file in the project root
     - Name it `Firebase Admin SDK Service Account.json`

## Usage

1. Start the Flask server:
   ```bash
   python app.py
   ```
2. The server will be available at `http://localhost:5000`

## API Endpoints

- `GET /search?query=<search_term>&provider=<provider_name>`
  - `provider` can be: `whoosh`, `mapbox`, `google_places`, or `all`
  - Returns a list of places matching the search query

## Development

- The search providers are implemented as separate classes inheriting from `SearchProvider`
- The `SearchOrchestrator` class combines results from multiple providers
- Place storage is handled by the `PlaceStorage` class (currently disabled)

## License

MIT 