"""Validated recipe data. External content is always rendered as plain text."""

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit


def safe_url(value: object, hosts: set[str] | None = None) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        url = urlsplit(value.strip())
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or any(ord(c) < 33 for c in value)
        ):
            return ""
        if hosts and url.hostname.lower() not in hosts:
            return ""
        return value.strip()
    except ValueError:
        return ""


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    instructions: str
    ingredients: tuple[str, ...] = ()
    photo: str = ""
    video: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_api(cls, data: dict) -> "Recipe":
        recipe_id = str(data.get("idMeal", ""))
        name = data.get("strMeal")
        if not recipe_id.isascii() or not recipe_id.isdigit() or len(recipe_id) > 12:
            raise ValueError("Invalid recipe ID")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Missing recipe name")
        ingredients = []
        for index in range(1, 21):
            item = data.get(f"strIngredient{index}")
            amount = data.get(f"strMeasure{index}")
            if isinstance(item, str) and item.strip():
                measure = amount.strip() if isinstance(amount, str) else ""
                ingredients.append(f"{item.strip()} — {measure}" if measure else item.strip())
        instructions = data.get("strInstructions")
        return cls(
            id=recipe_id,
            name=name.strip()[:200],
            instructions=instructions.strip() if isinstance(instructions, str) else "",
            ingredients=tuple(ingredients),
            photo=safe_url(data.get("strMealThumb"), {"www.themealdb.com", "themealdb.com"}),
            video=safe_url(data.get("strYoutube"), {"www.youtube.com", "youtube.com", "youtu.be"}),
            source=safe_url(data.get("strSource")),
        )
