import argparse, json, random, re
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
MODEL = "llama3.2:3b"
random.seed(42)

# Product types per category, with a price range for each
CATALOGUE = {
    "Electronics": [("laptop", (399, 1499)), ("wireless headphones", (39, 299)),
                    ("smart speaker", (29, 199)), ("4K TV", (299, 1299)), ("tablet", (149, 799))],
    "Outdoor & Sport": [("waterproof jacket", (49, 249)), ("hiking boots", (59, 199)),
                        ("2-person tent", (79, 349)), ("yoga mat", (15, 69)), ("running watch", (99, 399))],
    "Home & Kitchen": [("air fryer", (49, 199)), ("coffee machine", (79, 499)),
                       ("duvet", (29, 149)), ("blender", (29, 179)), ("robot vacuum", (149, 599))],
    "Toys & Gifts": [("science kit", (15, 59)), ("board game", (12, 49)),
                     ("building set", (19, 149)), ("remote-control car", (25, 99))],
    "Fashion": [("winter coat", (59, 299)), ("trainers", (39, 149)),
                ("backpack", (25, 119)), ("scarf", (12, 49))],
}
PER_TYPE = 13  # 23 types x 13 = 299 products

# One angle per product of each type, so the 13 versions differ
ANGLES = [
    "budget-friendly", "premium", "for beginners", "for professionals", "for kids",
    "eco-friendly", "compact", "for families", "for students", "gift idea",
    "high-performance", "lightweight", "long-lasting",
]

# Real brands to keep out of the catalogue (matched as whole words)
BANNED = ["gore", "goretex", "event", "apple", "samsung", "sony", "nike", "adidas",
          "lego", "dyson", "bose", "garmin", "fitbit", "ninja", "philips", "nespresso"]

used_names = set()


def write_listing(category, ptype, price, angle):
    """Ask the LLM for one product listing; retry if it fails our checks."""
    avoid = ", ".join(sorted(used_names)[-40:]) or "none"
    prompt = (
        f"Write a product listing for an online store. Product type: {ptype} ({category}), "
        f"price £{price}, positioned as: {angle}. Invent a distinctive product name that "
        f"is not similar to any of these: {avoid}. Do not mention any real brands, "
        "trademarks or branded materials. Do not start the description with 'Get ready'. "
        "Return JSON only, with keys: name, description (80-120 words: who it's for and "
        "key features), specs (an object with 3-5 key specs, consistent with the description, "
        "using UK metric units with the unit written in each value, e.g. '320g', '4.5L')."
    )
    for _ in range(4):
        try:
            r = client.chat.completions.create(
                model=MODEL, temperature=0.9,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            listing = json.loads(r.choices[0].message.content)
        except (json.JSONDecodeError, KeyError):
            continue

        text = json.dumps(listing).lower()
        name = str(listing.get("name", "")).strip()
        if not name:
            continue
        has_brand = any(re.search(rf"\b{b}\b", text) for b in BANNED)
        first_word = name.split()[0].lower()
        used_first = {n.split()[0] for n in used_names}
        if has_brand or first_word in used_first:
            continue

        used_names.add(name.lower())
        return listing
    return None  # all attempts failed


def load_existing(path):
    """Read products from an earlier run so we can carry on from where it stopped."""
    done_ids = set()
    try:
        with open(path) as existing:
            for line in existing:
                try:
                    p = json.loads(line)
                except json.JSONDecodeError:
                    continue  # ignore a half-written last line
                done_ids.add(p["id"])
                used_names.add(p["name"].lower())  # keep names unique across both runs
    except FileNotFoundError:
        pass
    return done_ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="stop after N products")
    parser.add_argument("--out", default="data/products.jsonl")
    parser.add_argument("--resume", action="store_true", help="keep existing products and continue")
    args = parser.parse_args()

    # Build the to-do list: one entry per product to generate
    jobs = [(c, t, rng, ANGLES[i]) for c, types in CATALOGUE.items()
            for t, rng in types for i in range(PER_TYPE)]
    if args.limit:
        random.shuffle(jobs)  # sample across categories for a quick test
        jobs = jobs[:args.limit]

    done_ids = load_existing(args.out) if args.resume else set()
    if args.resume:
        print(f"Resuming: {len(done_ids)} products already done")

    written, skipped = 0, 0
    with open(args.out, "a" if args.resume else "w") as f:
        for n, (category, ptype, (lo, hi), angle) in enumerate(jobs, start=1):
            # Always calculate prices, even for finished products, so the random
            # sequence matches an unbroken run
            price = round(random.uniform(lo, hi)) - 0.01
            bf_price = round(price * random.uniform(0.6, 0.9)) - 0.01
            if f"p{n:04d}" in done_ids:
                continue

            listing = write_listing(category, ptype, price, angle)
            if listing is None:
                skipped += 1
                print(f"{n}/{len(jobs)}  SKIPPED {ptype} ({angle})")
                continue

            product = {
                "id": f"p{n:04d}", "category": category, "type": ptype, "angle": angle,
                "name": listing["name"], "price": price, "black_friday_price": bf_price,
                "description": listing.get("description", ""),
                "specs": listing.get("specs", {}),
            }
            f.write(json.dumps(product) + "\n")
            f.flush()  # save each line straight away
            written += 1
            print(f"{n}/{len(jobs)}  {product['name']}")

    print(f"\nDone: {written} written, {skipped} skipped -> {args.out}")


if __name__ == "__main__":
    main()