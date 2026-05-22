from game.ai_content import apply_approved_content


def load_ai_content_on_startup() -> dict:
    try:
        return apply_approved_content(limit=200)
    except Exception as e:
        print(f"AI content load failed: {e}")
        return {"failed": 1}
