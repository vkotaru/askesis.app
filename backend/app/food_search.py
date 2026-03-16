"""
External food database search: USDA FoodData Central + Open Food Facts.
Used as fallback when local DB has few results.
"""

import logging
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
OFF_BASE = "https://world.openfoodfacts.org/cgi/search.pl"


def _map_category(raw: str | None) -> str | None:
    """Best-effort category mapping from external data."""
    if not raw:
        return None
    r = raw.lower()
    for kw, cat in [
        ("fruit", "fruit"), ("vegetable", "vegetable"), ("grain", "grain"),
        ("cereal", "grain"), ("bread", "grain"), ("rice", "grain"),
        ("dairy", "dairy"), ("milk", "dairy"), ("cheese", "dairy"),
        ("yogurt", "dairy"), ("meat", "protein"), ("poultry", "protein"),
        ("chicken", "protein"), ("fish", "protein"), ("seafood", "protein"),
        ("egg", "protein"), ("legume", "legume"), ("bean", "legume"),
        ("lentil", "legume"), ("nut", "nut"), ("seed", "nut"),
        ("oil", "oil"), ("fat", "oil"), ("butter", "oil"),
        ("beverage", "beverage"), ("drink", "beverage"), ("juice", "beverage"),
        ("snack", "snack"), ("candy", "snack"), ("chocolate", "snack"),
        ("spice", "spice"), ("herb", "spice"), ("sauce", "prepared"),
    ]:
        if kw in r:
            return cat
    return "other"


async def search_usda(query: str, limit: int = 10) -> list[dict]:
    """Search USDA FoodData Central. Requires USDA_API_KEY in settings."""
    settings = get_settings()
    api_key = getattr(settings, "usda_api_key", "") or ""
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{USDA_BASE}/foods/search",
                params={
                    "api_key": api_key,
                    "query": query,
                    "pageSize": limit,
                    "dataType": "Foundation,SR Legacy",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for food in data.get("foods", []):
            nutrients = {n["nutrientName"]: n.get("value", 0) for n in food.get("foodNutrients", [])}
            results.append({
                "external_id": f"usda:{food['fdcId']}",
                "name": food.get("description", "").title(),
                "brand": food.get("brandName"),
                "category": _map_category(food.get("foodCategory")),
                "serving_size": 100,
                "serving_unit": "g",
                "calories": round(nutrients.get("Energy", 0)),
                "protein_g": round(nutrients.get("Protein", 0), 1),
                "carbs_g": round(nutrients.get("Carbohydrate, by difference", 0), 1),
                "fat_g": round(nutrients.get("Total lipid (fat)", 0), 1),
                "fiber_g": round(nutrients.get("Fiber, total dietary", 0), 1) or None,
                "source": "usda",
            })
        return results
    except Exception as e:
        logger.warning(f"USDA search failed: {e}")
        return []


async def search_open_food_facts(query: str, limit: int = 10) -> list[dict]:
    """Search Open Food Facts. No API key needed."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                OFF_BASE,
                params={
                    "search_terms": query,
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": limit,
                    "fields": "product_name,brands,categories_tags,nutriments,serving_size",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for product in data.get("products", []):
            name = product.get("product_name", "").strip()
            if not name:
                continue

            n = product.get("nutriments", {})
            # Prefer per-100g values
            calories = n.get("energy-kcal_100g") or n.get("energy-kcal_serving")
            protein = n.get("proteins_100g") or n.get("proteins_serving")
            carbs = n.get("carbohydrates_100g") or n.get("carbohydrates_serving")
            fat = n.get("fat_100g") or n.get("fat_serving")
            fiber = n.get("fiber_100g") or n.get("fiber_serving")

            cats = product.get("categories_tags", [])
            cat_str = cats[0].replace("en:", "") if cats else None

            results.append({
                "external_id": f"off:{product.get('code', name)}",
                "name": name,
                "brand": product.get("brands"),
                "category": _map_category(cat_str),
                "serving_size": 100,
                "serving_unit": "g",
                "calories": round(calories) if calories else None,
                "protein_g": round(protein, 1) if protein else None,
                "carbs_g": round(carbs, 1) if carbs else None,
                "fat_g": round(fat, 1) if fat else None,
                "fiber_g": round(fiber, 1) if fiber else None,
                "source": "openfoodfacts",
            })
        return results
    except Exception as e:
        logger.warning(f"Open Food Facts search failed: {e}")
        return []


async def search_external(query: str, limit: int = 10) -> list[dict]:
    """Search both external databases, deduplicate by name."""
    import asyncio

    usda_results, off_results = await asyncio.gather(
        search_usda(query, limit),
        search_open_food_facts(query, limit),
    )

    # Combine, USDA first (generally more accurate), dedupe by lowercase name
    seen = set()
    combined = []
    for item in usda_results + off_results:
        key = item["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            combined.append(item)

    return combined[:limit]
