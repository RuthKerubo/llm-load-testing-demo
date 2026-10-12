import json, os
import psycopg
from pgvector.psycopg import register_vector
from fastembed import TextEmbedding

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://shop:shop@localhost:5432/shop")
PRODUCTS_FILE = os.getenv("PRODUCTS_FILE", "data/products.jsonl")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = 384  # size of the vectors this model produces


def to_text(p):
    """Turn one product into the text that gets embedded and later sent to the LLM."""
    specs = "; ".join(f"{str(k).strip()}: {v}" for k, v in p.get("specs", {}).items())
    return (
        f"{p['name']} - {p['type']} ({p['category']}), {p['angle']}.\n"
        f"Price £{p['price']:.2f}, Black Friday price £{p['black_friday_price']:.2f}.\n"
        f"{p['description']}\n"
        f"Specs: {specs}"
    )


def main():
    with open(PRODUCTS_FILE) as f:
        products = [json.loads(line) for line in f if line.strip()]
    texts = [to_text(p) for p in products]
    print(f"Loaded {len(products)} products")

    print("Embedding (the first run downloads the model)...")
    model = TextEmbedding(EMBED_MODEL)
    vectors = list(model.embed(texts))

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)  # lets psycopg send vectors to Postgres

        conn.execute("DROP TABLE IF EXISTS products")
        conn.execute(f"""
            CREATE TABLE products (
                id text PRIMARY KEY,
                name text NOT NULL,
                category text,
                type text,
                price numeric(8,2),
                black_friday_price numeric(8,2),
                content text NOT NULL,
                embedding vector({EMBED_DIM}) NOT NULL,
                search tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
            )
        """)

        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO products
                   (id, name, category, type, price, black_friday_price, content, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (p["id"], p["name"], p["category"], p["type"], p["price"],
                     p["black_friday_price"], text, vec)
                    for p, text, vec in zip(products, texts, vectors)
                ],
            )

        # HNSW index: fast "find the most similar vectors" (meaning search)
        conn.execute("CREATE INDEX ON products USING hnsw (embedding vector_cosine_ops)")
        # GIN index: fast keyword search on the tsvector column
        conn.execute("CREATE INDEX ON products USING gin (search)")

        count = conn.execute("SELECT count(*) FROM products").fetchone()[0]
        print(f"Stored {count} products in Postgres")


if __name__ == "__main__":
    main()