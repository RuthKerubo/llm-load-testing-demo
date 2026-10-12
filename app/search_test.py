import os, sys
import psycopg
from pgvector.psycopg import register_vector
from fastembed import TextEmbedding
from search import HYBRID_SQL, search_params, parse_question

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://shop:shop@localhost:5432/shop")
question = " ".join(sys.argv[1:]) or "waterproof jacket for hiking under £100"

model = TextEmbedding("BAAI/bge-small-en-v1.5")
qvec = next(model.query_embed(question))

with psycopg.connect(DATABASE_URL) as conn:
    register_vector(conn)
    rows = conn.execute(HYBRID_SQL, search_params(question, qvec, top_k=5)).fetchall()

max_price, tsq = parse_question(question)
print(f"Q: {question}\n   price limit: {max_price}  keywords: {tsq}\n")
for name, ptype, price, bf, content, score in rows:
    print(f"{score:.4f}  {name} ({ptype})  £{price} -> £{bf}")