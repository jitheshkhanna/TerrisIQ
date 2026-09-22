"""In-memory spatial stores backing the risk engines, one per city.

No PostGIS: the largest city corpus is ~20k features, which fits in memory and indexes
into a shapely STRtree in about a second.

Each city holds its layers twice:
  * WGS84 (EPSG:4326) - what we hand back to the map as GeoJSON
  * that city's UTM zone - what we measure on, so distances are true metres

The UTM zone is per city, not global. Mumbai and Ahmedabad sit in 43N, Chennai and
Hyderabad in 44N, Kolkata in 45N. Measuring Kolkata against Chennai's zone would skew
every distance the scoring depends on.

Stores load lazily and independently, so a Mumbai request never pays for Chennai's
25 MB of inundation polygons.
"""
import hashlib
import json
import os
import pickle
import threading
import time

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from app.core import cities as city_registry

WGS84 = "EPSG:4326"

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(os.path.dirname(HERE))
DATA_DIR = os.path.join(BACKEND_ROOT, "data")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
MANUAL_DIR = os.path.join(DATA_DIR, "manual")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

CACHE_VERSION = 6

# Explicit override; rarely needed now that staleness is only judged against sources
# that actually exist (see _cache_is_stale).
TRUST_CACHE = os.environ.get("TERRARISK_TRUST_CACHE", "").lower() in ("1", "true", "yes")

_transformers = {}
_transformer_lock = threading.Lock()


def _tx(epsg):
    """Cached forward/reverse transformers for a city's metric CRS."""
    with _transformer_lock:
        if epsg not in _transformers:
            crs = "EPSG:%d" % epsg
            _transformers[epsg] = (
                Transformer.from_crs(WGS84, crs, always_xy=True),
                Transformer.from_crs(crs, WGS84, always_xy=True),
            )
        return _transformers[epsg]


def to_utm(geom, epsg):
    fwd, _ = _tx(epsg)
    return shapely.transform(geom, lambda c: np.column_stack(fwd.transform(c[:, 0], c[:, 1])))


def point_utm(city, lat, lng):
    fwd, _ = _tx(city.epsg)
    x, y = fwd.transform(lng, lat)
    return Point(x, y)


def utm_to_wgs(city, x, y):
    _, rev = _tx(city.epsg)
    lng, lat = rev.transform(x, y)
    return lat, lng


class Layer:
    """A named collection of geometries with an STRtree over the metric copy."""

    def __init__(self, name, geoms_wgs, props, epsg):
        self.name = name
        self.epsg = epsg
        self.geoms_wgs = geoms_wgs
        self.props = props
        self.geoms_utm = [to_utm(g, epsg) for g in geoms_wgs]
        self.tree = STRtree(self.geoms_utm) if self.geoms_utm else None

    def __len__(self):
        return len(self.geoms_wgs)

    def containing(self, pt):
        if self.tree is None:
            return []
        return [int(i) for i in self.tree.query(pt, predicate="intersects")]

    def nearest(self, pt):
        if self.tree is None or not self.geoms_utm:
            return None, None
        idx = int(self.tree.nearest(pt))
        return idx, float(self.geoms_utm[idx].distance(pt))

    def within(self, pt, radius_m):
        if self.tree is None:
            return []
        hits = []
        for i in self.tree.query(pt.buffer(radius_m), predicate="intersects"):
            i = int(i)
            if self.geoms_utm[i].distance(pt) <= radius_m:
                hits.append(i)
        return hits

    def nearest_with_props(self, pt):
        idx, dist = self.nearest(pt)
        if idx is None:
            return None, None, None
        return idx, dist, self.props[idx]


def _load_geojson(path):
    with open(path) as fh:
        data = json.load(fh)
    geoms, props = [], []
    for feat in data.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
        except Exception:
            continue
        if g.is_empty:
            continue
        if not g.is_valid:
            g = g.buffer(0)
            if g.is_empty or not g.is_valid:
                continue
        geoms.append(g)
        props.append(feat.get("properties") or {})
    return geoms, props


def _load_points(path, lat_key="lat", lng_key="lng"):
    with open(path) as fh:
        records = json.load(fh)
    geoms = [Point(r[lng_key], r[lat_key]) for r in records]
    return geoms, records


# Curated point datasets. These are Chennai-only: no other city has an equivalent, and
# inventing one would be worse than scoring without it.
CHENNAI_POINT_FILES = {
    "industrial_clusters": "industrial_clusters.json",
    "dumpsites": "dumpsites.json",
    "firkas": "groundwater_firkas.json",
    "flood_context": "flood_context_localities.json",
}


class SpatialStore:
    """One city's layers, loaded once."""

    def __init__(self, city):
        self.city = city
        self.layers = {}
        self.load_seconds = 0.0
        self.loaded = False

    @property
    def cache_path(self):
        return os.path.join(CACHE_DIR, "%s.pkl" % self.city.slug)

    def _point_files(self):
        return CHENNAI_POINT_FILES if self.city.slug == "chennai" else {}

    def load(self, use_cache=True):
        if self.loaded:
            return self
        start = time.time()
        if use_cache and self._load_cache():
            self.loaded = True
            self.load_seconds = time.time() - start
            return self

        for name, filename in self.city.layers.items():
            path = os.path.join(PROCESSED_DIR, filename)
            if not os.path.exists(path):
                print("  ! %s/%s missing (%s)" % (self.city.slug, name, filename))
                self.layers[name] = Layer(name, [], [], self.city.epsg)
                continue
            geoms, props = _load_geojson(path)
            self.layers[name] = Layer(name, geoms, props, self.city.epsg)
            print("  %s/%-16s %6d features" % (self.city.slug, name, len(geoms)))

        for name, filename in self._point_files().items():
            path = os.path.join(MANUAL_DIR, filename)
            if not os.path.exists(path):
                self.layers[name] = Layer(name, [], [], self.city.epsg)
                continue
            geoms, props = _load_points(path)
            self.layers[name] = Layer(name, geoms, props, self.city.epsg)

        self._write_cache()
        self.loaded = True
        self.load_seconds = time.time() - start
        print("  %s ready in %.1fs" % (self.city.slug, self.load_seconds))
        return self

    # -- cache -----------------------------------------------------------
    @staticmethod
    def _fingerprint(path):
        """Content hash of a source file, or None if absent.

        Deliberately not mtime: uploading to a serverless host rewrites every mtime,
        which made a good cache look stale and left the API serving empty layers.
        """
        if not os.path.exists(path):
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _cache_signature(self):
        sig = {"version": CACHE_VERSION, "epsg": self.city.epsg}
        for name, filename in self.city.layers.items():
            sig[name] = self._fingerprint(os.path.join(PROCESSED_DIR, filename))
        for name, filename in self._point_files().items():
            sig[name] = self._fingerprint(os.path.join(MANUAL_DIR, filename))
        return sig

    def _cache_is_stale(self, stored):
        """Only decidable against sources we can see. A serverless deploy ships the cache
        without the source GeoJSON, and treating 'cannot tell' as stale would discard a
        good cache and serve empty layers."""
        if stored.get("version") != CACHE_VERSION or stored.get("epsg") != self.city.epsg:
            return True
        for name, fingerprint in self._cache_signature().items():
            if name in ("version", "epsg") or fingerprint is None:
                continue
            if stored.get(name) is not None and stored[name] != fingerprint:
                return True
        return False

    def _load_cache(self):
        if not os.path.exists(self.cache_path):
            return False
        try:
            with open(self.cache_path, "rb") as fh:
                blob = pickle.load(fh)
            if not TRUST_CACHE and self._cache_is_stale(blob.get("signature") or {}):
                print("  %s cache stale, rebuilding" % self.city.slug)
                return False
            for name, payload in blob["layers"].items():
                geoms = shapely.from_wkb(payload["wkb"])
                self.layers[name] = Layer(name, list(geoms), payload["props"], self.city.epsg)
            return True
        except Exception as exc:  # noqa: BLE001 - a bad cache must never be fatal
            print("  %s cache unreadable (%s)" % (self.city.slug, exc))
            return False

    def _write_cache(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            blob = {"signature": self._cache_signature(), "layers": {}}
            for name, layer in self.layers.items():
                blob["layers"][name] = {
                    "wkb": [shapely.to_wkb(g) for g in layer.geoms_wgs],
                    "props": layer.props,
                }
            tmp = self.cache_path + ".tmp"
            with open(tmp, "wb") as fh:
                pickle.dump(blob, fh, protocol=4)
            os.replace(tmp, self.cache_path)
        except Exception as exc:  # noqa: BLE001
            print("  could not write %s cache: %s" % (self.city.slug, exc))

    def layer(self, name):
        return self.layers.get(name) or Layer(name, [], [], self.city.epsg)

    def has(self, name):
        return len(self.layer(name)) > 0


_stores = {}
_stores_lock = threading.Lock()


def get_store(city):
    """The loaded store for a city, building it on first use."""
    with _stores_lock:
        store = _stores.get(city.slug)
        if store is None:
            store = SpatialStore(city)
            _stores[city.slug] = store
    store.load()
    return store


def loaded_slugs():
    with _stores_lock:
        return sorted(s for s, st in _stores.items() if st.loaded)


def preload(slugs=None):
    for slug in (slugs or list(city_registry.CITIES)):
        city = city_registry.get(slug)
        if city:
            get_store(city)
