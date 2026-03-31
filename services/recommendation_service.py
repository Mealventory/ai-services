def calculate_recipe_score(recipe_ingredients, user_inventory, expiring_items):
    matched = 0
    expiring_match = 0

    for ingredient in recipe_ingredients:
        if ingredient in user_inventory:
            matched += 1
        if ingredient in expiring_items:
            expiring_match += 1

    score = (matched * 2) + (expiring_match * 3)
    return score


def recommend_recipes(user_inventory, recipes, expiring_items):
    scored_recipes = []

    for recipe in recipes:
        score = calculate_recipe_score(
            recipe["ingredients"],
            user_inventory,
            expiring_items
        )

        scored_recipes.append({
            "name": recipe["name"],
            "score": score
        })

    # ort recipes by score (highest first)
    scored_recipes.sort(key=lambda x: x["score"], reverse=True)

    return scored_recipes