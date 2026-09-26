"""Headline sentiment: VADER plus a finance-specific lexicon boost."""
from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

FINANCE_LEXICON: dict[str, float] = {
    # bullish
    "beat": 1.8, "beats": 1.8, "surge": 2.2, "surges": 2.2, "soar": 2.4, "soars": 2.4, "rally": 1.8, "rallies": 1.8,
    "upgrade": 2.0, "upgraded": 2.0, "upgrades": 2.0, "outperform": 1.6, "record": 1.2, "buyback": 1.5,
    "raises": 1.2, "raised": 1.2, "bullish": 2.0, "breakout": 1.5, "jumps": 1.8, "climbs": 1.4, "gains": 1.4,
    "profit": 1.0, "profits": 1.0, "approval": 1.6, "approved": 1.6, "partnership": 1.0, "dividend": 0.8,
    "all-time high": 2.0, "guidance raised": 2.2, "strong demand": 1.8, "exceeds": 1.5,
    # bearish
    "miss": -1.8, "misses": -1.8, "missed": -1.8, "plunge": -2.6, "plunges": -2.6, "tumble": -2.2, "tumbles": -2.2,
    "downgrade": -2.2, "downgraded": -2.2, "downgrades": -2.2, "underperform": -1.8, "lawsuit": -1.8, "sued": -1.8,
    "probe": -1.6, "investigation": -1.6, "recall": -1.8, "bankruptcy": -3.0, "bankrupt": -3.0, "default": -2.0,
    "layoffs": -1.4, "cuts guidance": -2.4, "guidance cut": -2.4, "slump": -2.0, "slumps": -2.0, "sinks": -2.0,
    "falls": -1.2, "drops": -1.2, "bearish": -2.0, "sell-off": -2.0, "selloff": -2.0, "fraud": -3.0, "hack": -2.4,
    "hacked": -2.4, "exploit": -2.0, "delisting": -2.4, "halted": -1.6, "warning": -1.4, "warns": -1.4,
    "sec charges": -2.6, "short report": -2.2, "dilution": -1.6, "offering": -0.8, "crash": -2.8, "crashes": -2.8,
}


class SentimentScorer:
    def __init__(self, extra_lexicon: dict[str, float] | None = None):
        self._analyzer = SentimentIntensityAnalyzer()
        lex = dict(FINANCE_LEXICON)
        if extra_lexicon:
            lex.update(extra_lexicon)
        # VADER's lexicon is single-token; multi-word phrases are handled by substitution below.
        self._phrases = {k: v for k, v in lex.items() if " " in k or "-" in k}
        self._analyzer.lexicon.update({k: v for k, v in lex.items() if k not in self._phrases})

    def score(self, text: str) -> float:
        """Compound score in [-1, 1]; > 0.2 is positive, < -0.2 negative."""
        if not text or not text.strip():
            return 0.0
        lowered = text.lower()
        boost = 0.0
        for phrase, val in self._phrases.items():
            if phrase in lowered:
                boost += val / 4.0  # phrase weights on VADER's [-4, 4] scale
        compound = self._analyzer.polarity_scores(text)["compound"]
        return max(-1.0, min(1.0, compound + boost))

    @staticmethod
    def label(score: float) -> str:
        if score >= 0.2:
            return "positive"
        if score <= -0.2:
            return "negative"
        return "neutral"
