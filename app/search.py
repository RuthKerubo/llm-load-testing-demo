import re

# Picks up "under £100", "below 50", "less than £80", "up to £200"...
PRICE_RE = re.compile(
    r"(?:under|below|less than|cheaper than|up to|max(?:imum)?|within)\s*£?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[a-zA-Z]{3,}")


def parse_question(question):
    """Pull out a price limit (if any) and the words for keyword search."""
    m = PRICE_RE.search(question)
    max_price = float(m.group(1)) if m else None
    words = WORD_RE.findall(question)
    tsquery = " | ".join(words)  # match ANY of the words, not all of them
    return max_price, tsquery


# Hybrid search: price filter, then vector + keyword rankings merged with
# Reciprocal Rank Fusion (each list scores 1 / (60 + rank); scores are added up)
HYBRID_SQL = """
WITH filtered AS (
    SELECT * FROM products
    WHERE %(max_price)s::numeric IS NULL OR black_friday_price <= %(max_price)s::numeric
),
vec AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> %(qvec)s) AS rank
    FROM filtered
    ORDER BY embedding <=> %(qvec)s
    LIMIT %(pool)s
),
txt AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank_cd(search, q) DESC) AS rank
    FROM filtered, to_tsquery('english', %(tsq)s) AS q
    WHERE search @@ q
    ORDER BY ts_rank_cd(search, q) DESC
    LIMIT %(pool)s
),
fused AS (
    SELECT id, sum(1.0 / (60 + rank)) AS score
    FROM (SELECT * FROM vec UNION ALL SELECT * FROM txt) AS ranked
    GROUP BY id
)
SELECT p.name, p.type, p.price, p.black_friday_price, p.content, f.score
FROM fused f JOIN products p USING (id)
ORDER BY f.score DESC
LIMIT %(top_k)s
"""


def search_params(question, qvec, top_k, pool=20):
    """Build the parameters for HYBRID_SQL from a question and its vector."""
    max_price, tsquery = parse_question(question)
    return {"qvec": qvec, "tsq": tsquery, "max_price": max_price,
            "top_k": top_k, "pool": pool}