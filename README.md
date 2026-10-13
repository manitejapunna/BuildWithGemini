# travel-concierge

An intelligent, interactive travel discovery and planning concierge built with the Google Agent Development Kit (ADK) and Gemini 2.5 Flash.

`travel-concierge` conducts progressive, one-question-at-a-time discovery conversations to understand traveler preferences (companions, dining/allergies, accommodation style, packing habits, and passport validity) without hallucinations. It grounds recommendations using real-time APIs, Google Cloud services, and a Firestore destination catalog.

---

## What the Agent Actually Does

The agent's capabilities are strictly backed by the tools and cloud backends implemented in `app/`:

### 1. Interactive Traveler Profiling & Grounding
- **Progressive Discovery**: Follows a strict one-question-at-a-time conversational protocol to capture traveler profiles incrementally into session state.
- **Zero-Hallucination Guardrails**: Checks existing profile state before suggesting recommendations and never invents dining habits, allergies, or travel constraints.
- **Trip Preparation Checklist**: Manages an interactive preparation task list (`manage_trip_checklist`) tailored to destination requirements.

### 2. Google Cloud Integrations
- **Vertex AI Memory Bank (`VertexAiMemoryBankService`)**:
  - Automatically captures durable user facts, dietary requirements, and past trip preferences across sessions (`generate_memories_callback` via `add_session_to_memory`).
  - Preloads long-term memories at the beginning of each turn via `PreloadMemoryTool` to personalize recommendations across separate visits.
- **Google Cloud Firestore**:
  - Connects to native Firestore database `(default)` to query curated destinations (`list_travel_destinations`), retrieve in-depth regional guides (`get_destination_details`), and persist new traveler destinations (`add_travel_destination`).
- **Google Cloud Storage (Public Bucket)**:
  - Backed by public bucket `gs://travel-concierge-assets-qwiklabs-gcp-04-d718c29e3c1e` with `roles/storage.objectViewer` for hosting and serving static travel media.
- **Google Maps Platform (Geocoding & Places New)**:
  - **`geocode_address`**: Converts street addresses or landmark names into exact geographic latitude/longitude coordinates via Google Maps Geocoding REST API.
  - **`search_nearby_places`**: Queries Google Maps Places API (New) (`places:searchNearby`) using field masks (`displayName`, `formattedAddress`, `location`) to discover real restaurants, cafes, hotels, and attractions around coordinates.

### 3. Real-Time Public APIs & Routing
- **Open-Meteo Weather**: `get_destination_weather` fetches real-time meteorological conditions, 5-day temperature forecasts, and dynamic packing recommendations.
- **Open Exchange Rates**: `convert_currency_and_estimate_budget` delivers live currency conversions and daily travel spending breakdowns.
- **Great-Circle Route Estimator**: `calculate_flight_duration_and_route` computes distance, estimated nonstop jet air time, and advance flight booking windows.
- **Wikipedia REST API**: `get_destination_wiki_summary` fetches factual encyclopedia extracts, historical backgrounds, official desktop links, and landmark images for attractions.
- **Visa & Passport Verifier**: `check_visa_and_passport_requirements` calculates passport 6-month validity compliance and Schengen/international entry guidelines.

---

## Status of Planned Features

| Feature | Status | Notes |
| :--- | :--- | :--- |
| **Cross-Session Memory Bank** | **Implemented** | Wired via `PreloadMemoryTool` and `after_agent_callback`. |
| **Firestore Database Catalog** | **Implemented** | Seeded with top world destinations (`travel_destinations`). |
| **Cloud Storage Public Bucket** | **Implemented** | Configured with uniform bucket-level access & public read. |
| **Google Maps Geocoding & Places** | **Implemented** | Live REST integration for addresses & nearby discovery. |
| **Live Weather & Currency Conversion** | **Implemented** | 100% free live API endpoints without rate gates. |
| **Interactive Custom Frontend** | **Implemented** | FastAPI proxy + modern HTML/JS interface in `frontend/`. |
| **Imagen 3 Image Generation** | *Planned, not yet implemented* | Scenic image generation tool to be wired in future iteration. |
| **A2UI Rich Card Rendering** | *Planned, not yet implemented* | Agent currently outputs markdown; A2UI renderer adapter planned. |

---

## Project Structure

```
travel-concierge/
├── app/
│   ├── agent.py               # Root ADK agent, tools, instructions & callbacks
│   ├── fast_api_app.py        # FastAPI server with A2A & Reasoning Engine routes
│   └── app_utils/
│       ├── services.py        # Shared Session, Artifact, and Memory Bank services
│       ├── a2a.py             # A2A Protocol router bindings
│       └── reasoning_engine_adapter.py # Adapter for Cloud Console playground
├── frontend/
│   ├── main.py                # Standalone chat web frontend proxy
│   └── static/
│       └── index.html         # Responsive web UI with persistent input & reset
├── scripts/
│   └── seed_firestore.py      # Firestore destination database seeding script
├── deployment_metadata.json   # Remote Agent Runtime deployment metadata
├── agents-cli-manifest.yaml   # agents-cli project specification
└── pyproject.toml             # Python dependencies and build configuration
```

---

## Setup & Local Run Instructions

### Prerequisites
- Python 3.11+
- `uv` package manager (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Google Cloud SDK (`gcloud`) authenticated with a project having Vertex AI & Firestore enabled

### 1. Environment Configuration
Ensure your local `.env` contains your project settings and keys:

```env
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=<YOUR_GCP_PROJECT_ID>
GOOGLE_CLOUD_LOCATION=us-central1
GCS_BUCKET_NAME=<YOUR_GCS_BUCKET_NAME>
GOOGLE_MAPS_API_KEY=<YOUR_GOOGLE_MAPS_API_KEY>
```

### 2. Install Dependencies

```bash
uv sync
```

### 3. Seed Firestore Database
Populate the initial destination catalog in your Firestore instance:

```bash
uv run python scripts/seed_firestore.py
```

### 4. Run the Agent Locally

#### Option A: ADK Web Playground (with Memory Bank)
To test the agent with live cross-session Memory Bank in the ADK Web UI:

```bash
uv run adk web . --port 8080 --reload_agents --memory_service_uri=agentengine://<MEMORY_BANK_ID>
```

#### Option B: Standalone Web Frontend
To run the included responsive travel chat interface:

```bash
PORT=8080 uv run python frontend/main.py
```

---

## Deployment to Vertex AI Agent Platform

To deploy or update the agent on Vertex AI Agent Runtime:

```bash
agents-cli deploy --project <YOUR_GCP_PROJECT_ID> --region us-central1
```
