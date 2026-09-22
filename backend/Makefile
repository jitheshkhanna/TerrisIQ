VENV := .venv/bin
.PHONY: data ingest osm manual layers validate serve clean-cache

## Full data pipeline. Every step caches, so re-running is cheap.
data: ingest osm manual layers
	@echo ""
	@echo "Data ready. Start the API with:  make serve"

ingest:      ## Download the GCC KMLs and convert them to GeoJSON
	$(VENV)/python scripts/ingest_kml.py

osm:         ## Pull waterbodies, industrial land use, coastline and landfills from Overpass
	$(VENV)/python scripts/fetch_osm.py

manual:      ## Emit the curated CPCB / CGWB datasets
	$(VENV)/python scripts/build_manual.py

layers:      ## Simplify GeoJSON for the browser
	$(VENV)/python scripts/build_map_layers.py

validate:    ## Ground-truth and latency checks
	$(VENV)/python scripts/validate_flood_layer.py
	@echo ""
	$(VENV)/python scripts/validate_scoring.py

serve:       ## Run the API on :8000
	$(VENV)/python -m uvicorn app.main:app --reload --port 8000

clean-cache: ## Drop the derived spatial cache (raw downloads are kept)
	rm -f data/spatial_cache.pkl
