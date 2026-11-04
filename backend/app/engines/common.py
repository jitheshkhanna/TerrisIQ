"""Shared helpers for the risk engines."""
import math

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two WGS84 points."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


class ScoreBuilder:
    """Accumulates scored components, warnings and provenance for one risk dimension."""

    def __init__(self, dimension):
        self.dimension = dimension
        self.components = []
        self.warnings = []
        self.facts = []
        self.details = {}
        self._confidence = "high"

    def add(self, key, points, label, cap=None, **detail):
        if cap is not None:
            points = min(points, cap)
        points = round(float(points), 1)
        self.components.append({"key": key, "points": points, "label": label})
        if detail:
            self.details[key] = detail
        return points

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def fact(self, text, level):
        """A glanceable finding of five words or fewer, for the on-screen card.

        The full sentence goes through warn() and lands in the PDF. Levels: high, medium,
        low (minor), good (reassuring), info (a data gap, not a risk).
        """
        entry = {"text": text, "level": level}
        if entry not in self.facts:
            self.facts.append(entry)

    def has_signal(self):
        """Any fact that says something about risk, as opposed to a data gap."""
        return any(f["level"] in ("high", "medium", "low", "good") for f in self.facts)

    def has_gap(self):
        return any(f["level"] == "info" for f in self.facts)

    def downgrade(self, level):
        if CONFIDENCE_ORDER[level] < CONFIDENCE_ORDER[self._confidence]:
            self._confidence = level

    @property
    def confidence(self):
        return self._confidence

    def score(self):
        total = sum(c["points"] for c in self.components)
        return int(max(0, min(100, round(total))))

    def build(self):
        return {
            "score": self.score(),
            "confidence": self.confidence,
            "warnings": self.warnings,
            "facts": self.facts,
            "components": self.components,
            "details": self.details,
        }
